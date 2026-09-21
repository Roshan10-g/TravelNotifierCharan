"""
TravelNotifier Telegram Bot
An automated, zero-stress multi-modal commute autopilot.
Fires daily commute prompts, listens to live location, and triggers mode-aware
alerts (1 stop before for Metro, 500m for Bus/Other).
Includes confirmation buttons, re-enter buttons, and undo capabilities for every stop.
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import re
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Any

from telegram import (
    Update,
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ExtBot,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    PicklePersistence,
    filters
)

import config
import database
import geocoder
import metro_data
import journey_engine
import scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states for /setup, /settime, /setstops
(
    STATE_SETUP_CHOICE,
    STATE_MORNING_TIME,
    STATE_EVENING_TIME,
    STATE_ACTIVE_DAYS,
    STATE_ORIGIN_SEARCH,
    STATE_ORIGIN_PICK,
    STATE_ORIGIN_CONFIRM,
    STATE_MID_CHOICE,
    STATE_MID_SEARCH,
    STATE_MID_PICK,
    STATE_MID_CONFIRM,
    STATE_DEST_SEARCH,
    STATE_DEST_PICK,
    STATE_DEST_CONFIRM
) = range(14)


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def parse_time_string(text: str) -> str:
    """Parses various time formats ('8:15 AM', '08:15', '8.15pm', '20:30') into 'HH:MM' (24-hour)."""
    text = text.strip().upper()
    try:
        if "AM" in text or "PM" in text:
            dt = datetime.strptime(text.replace(".", ":"), "%I:%M %p" if " " in text else "%I:%M%p")
            return dt.strftime("%H:%M")
        else:
            dt = datetime.strptime(text.replace(".", ":"), "%H:%M")
            return dt.strftime("%H:%M")
    except Exception:
        m = re.match(r"^(\d{1,2})[:.]?(\d{2})?\s*(AM|PM)?$", text)
        if m:
            h = int(m.group(1))
            m_min = int(m.group(2) or 0)
            ampm = m.group(3)
            if ampm == "PM" and h < 12:
                h += 12
            elif ampm == "AM" and h == 12:
                h = 0
            return f"{h:02d}:{m_min:02d}"
    return "08:00"


def format_time_12h(time_24h: str) -> str:
    """Converts '08:15' to '8:15 AM'."""
    try:
        dt = datetime.strptime(time_24h, "%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return time_24h


def get_maps_url(stops: List[Dict]) -> str:
    """Generates a Google Maps Transit navigation URL for the stops."""
    if len(stops) < 2:
        return ""
    origin = f"{stops[0]['lat']},{stops[0]['lng']}"
    dest = f"{stops[-1]['lat']},{stops[-1]['lng']}"
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&travelmode=transit"
    return url


# =====================================================================
# COMMUTE PROMPT (MORNING & EVENING)
# =====================================================================

def get_bot_instance(bot_or_context):
    if isinstance(bot_or_context, (Bot, ExtBot)):
        return bot_or_context
    if hasattr(bot_or_context, "bot") and isinstance(getattr(bot_or_context, "bot"), (Bot, ExtBot)):
        return getattr(bot_or_context, "bot")
    return bot_or_context


async def send_commute_prompt(bot_or_context, user_id: int, direction: str = "morning"):
    bot = get_bot_instance(bot_or_context)
    user = database.get_or_create_user(user_id)
    stops = database.get_user_route(user_id, direction)

    dir_title = "Morning Commute ☀️" if direction == "morning" else "Evening Commute 🌆"
    dest_type = "Office" if direction == "morning" else "Home"

    if not stops:
        msg = (
            f"<b>{dir_title} Alert!</b>\n\n"
            f"You haven't configured your commute route yet.\n"
            f"Tap /setstops or /setup to configure your stops in 60 seconds!"
        )
        await bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.HTML)
        return

    route_display = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in stops])

    message_text = (
        f"<b>{dir_title}</b>\n"
        f"Ready to start your travel to {dest_type}?\n\n"
        f"🛣️ <b>Route:</b>\n{route_display}\n\n"
        f"Please select an option:"
    )

    keyboard = [
        [
            InlineKeyboardButton("🚀 Start Journey", callback_data=f"journey_start_{direction}"),
        ],
        [
            InlineKeyboardButton("🏠 WFH", callback_data=f"journey_wfh_{direction}"),
            InlineKeyboardButton("🏖️ On Leave", callback_data=f"journey_leave_{direction}")
        ],
        [
            InlineKeyboardButton("⏰ Snooze (+30 mins)", callback_data=f"journey_snooze_{direction}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await bot.send_message(
        chat_id=user_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )


# =====================================================================
# CALLBACK QUERY HANDLER (Button clicks)
# =====================================================================

async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # 1. START JOURNEY
    if data.startswith("journey_start_"):
        direction = data.split("_")[-1]
        database.start_journey(user_id, direction)
        stops = database.get_user_route(user_id, direction)

        maps_url = get_maps_url(stops)
        keyboard = []
        if maps_url:
            keyboard.append([InlineKeyboardButton("🗺️ Open Route in Google Maps", url=maps_url)])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        first_stop = stops[0]["stop_name"] if stops else "Source"
        next_stop = stops[1]["stop_name"] if len(stops) > 1 else "Destination"
        next_mode = stops[1].get("mode", "metro").capitalize() if len(stops) > 1 else "Transit"

        start_text = (
            f"🚀 <b>Journey Started ({direction.capitalize()})!</b>\n\n"
            f"📍 Starting from: <b>{first_stop}</b>\n"
            f"👉 First target stop: <b>{next_stop}</b> ({next_mode})\n\n"
            f"📡 <b>To enable automatic stop notifications:</b>\n"
            f"1. Tap the 📎 <b>Attachment</b> icon below\n"
            f"2. Select <b>Location</b> ➔ <b>'Share My Live Location for 1 Hour'</b>\n\n"
            f"💡 <i>I will run in the background and alert you 1 stop before your Metro stops and 500m before your Bus stops!</i>"
        )
        await query.edit_message_text(text=start_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

    # 2. WFH
    elif data.startswith("journey_wfh_"):
        database.end_journey(user_id)
        text = (
            f"🏠 <b>Work From Home noted!</b>\n\n"
            f"Have a great day, {user_name}! No tracking alerts will be sent today."
        )
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML)

    # 3. ON LEAVE
    elif data.startswith("journey_leave_"):
        database.end_journey(user_id)
        text = (
            f"🏖️ <b>Leave / Holiday noted!</b>\n\n"
            f"Enjoy your day off! See you on your next working day."
        )
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML)

    # 4. SNOOZE (+30 mins)
    elif data.startswith("journey_snooze_"):
        direction = data.split("_")[-1]
        scheduler.snooze_user_prompt(user_id, direction, lambda u, d: send_commute_prompt(context.bot, u, d), minutes=30)
        now_tz = datetime.now(pytz.timezone(config.TIMEZONE))
        ping_time = (now_tz + timedelta(minutes=30)).strftime("%I:%M %p")

        text = (
            f"⏰ <b>Snoozed for 30 minutes!</b>\n\n"
            f"I'll ping you again around <b>{ping_time}</b>.\n"
            f"💡 <i>(You can also just send <b>'Hi'</b> whenever you leave earlier!)</i>"
        )
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML)


# =====================================================================
# LIVE LOCATION LISTENER
# =====================================================================

async def on_location_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.edited_message or update.message
    if not msg or not msg.location:
        return

    user_id = msg.from_user.id
    loc = msg.location
    live_lat = loc.latitude
    live_lng = loc.longitude

    result = journey_engine.process_location_update(user_id, live_lat, live_lng)
    if result and result.should_notify:
        await context.bot.send_message(
            chat_id=user_id,
            text=result.message,
            parse_mode=ParseMode.HTML
        )


# =====================================================================
# COMMAND HANDLERS
# =====================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    database.get_or_create_user(user.id, user.first_name, user.username or "")

    welcome_text = (
        f"👋 Hello <b>{user.first_name}</b>!\n\n"
        f"Welcome to <b>TravelNotifier</b> — your personal commute autopilot.\n\n"
        f"✨ <b>What I do for you:</b>\n"
        f"• Ping you every weekday with <b>[Start] [WFH] [Leave] [Snooze]</b>\n"
        f"• Alert you <b>1 Stop Before</b> your Metro deboarding / interchange\n"
        f"• Alert you <b>500m Before</b> your Bus stops & Destination\n"
        f"• Confirmation & Re-enter buttons so you never save the wrong stop!\n"
        f"• Automatically switch for your evening return commute!\n\n"
        f"⚡ <b>Quick Commands:</b>\n"
        f"/settime - Change alert timings only (Morning & Evening)\n"
        f"/setstops - Change or re-enter your travel stops only\n"
        f"/setup - Commute settings menu (Timings, Stops, or Full Setup)\n"
        f"/myroute - View your saved morning & evening routes\n"
        f"/test - Trigger a commute prompt right now\n\n"
        f"💬 Or just send <b>'Hi'</b> anytime to start your journey!"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def cmd_myroute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = database.get_or_create_user(user_id)
    morning_stops = database.get_user_route(user_id, "morning")
    evening_stops = database.get_user_route(user_id, "evening")

    if not morning_stops:
        await update.message.reply_text(
            "⚠️ You haven't set up your route yet!\nTap /setstops or /setup to configure your daily commute.",
            parse_mode=ParseMode.HTML
        )
        return

    m_time_str = format_time_12h(user.get("morning_time", "08:00"))
    e_time_str = format_time_12h(user.get("evening_time", "18:30"))
    days_str = user.get("active_days", "mon-fri").upper()

    def render_stops(stops):
        lines = []
        for i, s in enumerate(stops):
            icon = "🚇" if s.get("mode") == "metro" else "🚌"
            tag = "Origin" if i == 0 else ("Destination" if i == len(stops) - 1 else "Transfer / Mid")
            lines.append(f"  {icon} <b>{s['stop_name']}</b> ({tag})")
        return "\n".join(lines)

    text = (
        f"📋 <b>Your Commute Profile:</b>\n\n"
        f"⏰ <b>Schedule:</b>\n"
        f"• Morning: <b>{m_time_str}</b>\n"
        f"• Evening: <b>{e_time_str}</b>\n"
        f"• Active Days: <b>{days_str}</b>\n\n"
        f"☀️ <b>Morning Route (Home ➔ Office):</b>\n"
        f"{render_stops(morning_stops)}\n\n"
        f"🌆 <b>Evening Route (Office ➔ Home):</b>\n"
        f"{render_stops(evening_stops)}\n\n"
        f"Tap /setstops anytime to edit stops!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    database.get_or_create_user(user_id, update.effective_user.first_name)
    await send_commute_prompt(context.bot, user_id, "morning")


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    user_id = update.effective_user.id
    user = database.get_or_create_user(user_id, update.effective_user.first_name)

    if text in ["hi", "hello", "hey", "start", "commute", "travel"]:
        now_hour = datetime.now(pytz.timezone(config.TIMEZONE)).hour
        direction = "evening" if now_hour >= 15 else "morning"
        await send_commute_prompt(context.bot, user_id, direction)
        return

    # Check if user has route set
    has_route = database.has_user_route(user_id)
    if not has_route:
        results = geocoder.search_locations(update.message.text.strip(), limit=4)
        if results:
            keyboard = []
            for idx, r in enumerate(results):
                keyboard.append([InlineKeyboardButton(f"{idx + 1}. {r['display_title']}", callback_data=f"quick_pick_{idx}")])
            keyboard.append([InlineKeyboardButton("📍 Tap to Start Full /setstops", callback_data="start_setstops_now")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            context.user_data["search_results"] = results
            await update.message.reply_text(
                f"🔍 <b>Found matching locations for '{update.message.text.strip()}':</b>\n\n"
                f"To configure your commute, tap <b>/setstops</b> or choose an option below:",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"👋 Hello {user.get('first_name', '')}!\n\n"
                f"Tap <b>/setstops</b> to configure your route, or send <b>'Hi'</b> to start!",
                parse_mode=ParseMode.HTML
            )
    else:
        await update.message.reply_text(
            f"👋 Hello {user.get('first_name', '')}!\n\n"
            f"Your commute is already saved! 🚆\n"
            f"• Send <b>'Hi'</b> or /test to test your commute prompt\n"
            f"• Tap /myroute to view your saved stops\n"
            f"• Tap /setstops anytime to edit stops",
            parse_mode=ParseMode.HTML
        )


# =====================================================================
# /setup, /settime & /setstops CONVERSATION WIZARD
# =====================================================================

async def setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = database.get_or_create_user(user_id, update.effective_user.first_name)

    context.user_data["setup"] = {
        "morning_time": user.get("morning_time", "08:00"),
        "evening_time": user.get("evening_time", "18:30"),
        "active_days": user.get("active_days", "mon,tue,wed,thu,fri"),
        "stops": []
    }

    if database.has_user_route(user_id):
        keyboard = [
            ["⏰ Change Timings Only"],
            ["📍 Change Stops Only"],
            ["🔄 Full Setup (Times + Stops)"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"🛠️ <b>Commute Settings Menu</b>\n\n"
            f"Current Schedule:\n"
            f"• Morning: <b>{format_time_12h(user['morning_time'])}</b>\n"
            f"• Evening: <b>{format_time_12h(user['evening_time'])}</b>\n"
            f"• Days: <b>{user['active_days'].upper()}</b>\n\n"
            f"What would you like to update?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_SETUP_CHOICE
    else:
        keyboard = [
            ["07:30 AM", "08:00 AM"],
            ["08:30 AM", "09:00 AM"],
            ["Custom Time"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "🛠️ <b>Commute Setup Wizard</b>\n\n"
            "<b>Step 1 of 5:</b> What time do you start for work in the <b>Morning</b>?\n"
            "Choose an option below or type your time (e.g. <code>8:15 AM</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_MORNING_TIME


async def setup_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lower()
    setup_data = context.user_data.setdefault("setup", {"stops": []})

    if "tim" in raw or "time" in raw or "clock" in raw or "hour" in raw:
        setup_data["time_only"] = True
        keyboard = [
            ["07:30 AM", "08:00 AM"],
            ["08:30 AM", "09:00 AM"],
            ["Custom Time"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "⏰ <b>Change Morning Departure Time</b>\n\n"
            "What time do you start for work in the <b>Morning</b>?\n"
            "Choose an option below or type your time (e.g. <code>8:15 AM</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_MORNING_TIME

    elif "stop" in raw or "route" in raw or "station" in raw:
        return await setup_start_stops_direct(update, context)

    else:
        setup_data["full_setup"] = True
        keyboard = [
            ["07:30 AM", "08:00 AM"],
            ["08:30 AM", "09:00 AM"],
            ["Custom Time"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "🔄 <b>Full Setup: Step 1 of 5</b>\n\n"
            "What time do you start for work in the <b>Morning</b>?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_MORNING_TIME


async def setup_start_time_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct entry point via /settime to change schedule timings only."""
    user_id = update.effective_user.id
    user = database.get_or_create_user(user_id, update.effective_user.first_name)

    context.user_data["setup"] = {
        "morning_time": user.get("morning_time", "08:00"),
        "evening_time": user.get("evening_time", "18:30"),
        "active_days": user.get("active_days", "mon,tue,wed,thu,fri"),
        "time_only": True,
        "stops": []
    }

    keyboard = [
        ["07:30 AM", "08:00 AM"],
        ["08:30 AM", "09:00 AM"],
        ["Custom Time"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "⏰ <b>Change Commute Timings</b>\n\n"
        "What time do you start for work in the <b>Morning</b>?\n"
        "Choose an option below or type your time (e.g. <code>8:15 AM</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_MORNING_TIME


async def setup_start_stops_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct entry point via /setstops to immediately set route stops."""
    user_id = update.effective_user.id
    user = database.get_or_create_user(user_id, update.effective_user.first_name)

    context.user_data["setup"] = {
        "morning_time": user.get("morning_time", "08:00"),
        "evening_time": user.get("evening_time", "18:30"),
        "active_days": user.get("active_days", "mon,tue,wed,thu,fri"),
        "stops": []
    }
    context.user_data.pop("pending_stop", None)

    await update.message.reply_text(
        "📍 <b>Where do you START your morning journey?</b>\n\n"
        "Type your station or bus stop name (e.g. <code>DSNR</code>, <code>Miyapur</code>, <code>Kukatpally</code>)\n"
        "<i>Or drop a location pin 📍 using the 📎 attachment icon!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return STATE_ORIGIN_SEARCH


async def setup_morning_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    setup_data = context.user_data.setdefault("setup", {"stops": []})

    if raw == "📍 Set Route Stops Directly":
        return await setup_start_stops_direct(update, context)

    if raw == "Custom Time":
        await update.message.reply_text("Please type your morning departure time (e.g. <code>8:15 AM</code>):", parse_mode=ParseMode.HTML)
        return STATE_MORNING_TIME

    time_24 = parse_time_string(raw)
    setup_data["morning_time"] = time_24

    keyboard = [
        ["05:30 PM", "06:00 PM"],
        ["06:30 PM", "07:00 PM"],
        ["07:30 PM", "Custom Time"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        f"✅ Morning time set to <b>{format_time_12h(time_24)}</b>.\n\n"
        "<b>Step 2 of 3:</b> What time do you start your return journey in the <b>Evening</b>?\n"
        "Choose an option below or type your time (e.g. <code>6:45 PM</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_EVENING_TIME


async def setup_evening_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    setup_data = context.user_data.setdefault("setup", {"stops": []})

    if raw == "Custom Time":
        await update.message.reply_text("Please type your evening return time (e.g. <code>6:45 PM</code>):", parse_mode=ParseMode.HTML)
        return STATE_EVENING_TIME

    time_24 = parse_time_string(raw)
    setup_data["evening_time"] = time_24

    keyboard = [
        ["Keep Current Days"],
        ["Mon-Fri (Weekdays)"],
        ["Mon-Sat (6 Days)"],
        ["Everyday"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        f"✅ Evening time set to <b>{format_time_12h(time_24)}</b>.\n\n"
        "<b>Step 3 of 3:</b> Which days do you travel to work?",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_ACTIVE_DAYS


async def setup_active_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    raw = update.message.text.strip().lower()
    setup_data = context.user_data.setdefault("setup", {"stops": []})

    if "keep" in raw or "current" in raw:
        user = database.get_or_create_user(user_id)
        days = user.get("active_days", "mon,tue,wed,thu,fri")
    elif "mon-sat" in raw or "6" in raw:
        days = "mon,tue,wed,thu,fri,sat"
    elif "everyday" in raw or "all" in raw:
        days = "mon,tue,wed,thu,fri,sat,sun"
    else:
        days = "mon,tue,wed,thu,fri"

    setup_data["active_days"] = days

    # If time_only OR (user already has route and didn't ask for full setup): FINISH IMMEDIATELY!
    if setup_data.get("time_only") or (database.has_user_route(user_id) and not setup_data.get("full_setup")):
        m_time = setup_data.get("morning_time", "08:00")
        e_time = setup_data.get("evening_time", "18:30")
        database.update_user_schedule(user_id, m_time, e_time, days)
        scheduler.schedule_user_commute(context.bot, user_id, lambda u, d: send_commute_prompt(context.bot, u, d))

        stops = database.get_user_route(user_id, "morning")
        route_str = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in stops]) if stops else "Not configured"

        context.user_data.pop("setup", None)

        await update.message.reply_text(
            f"🎉 <b>Schedule Timings Updated!</b>\n\n"
            f"⏰ <b>New Schedule:</b>\n"
            f"• Morning Ping: <b>{format_time_12h(m_time)}</b> ({days.upper()})\n"
            f"• Evening Ping: <b>{format_time_12h(e_time)}</b> ({days.upper()})\n\n"
            f"🛣️ <b>Your Saved Route (Unchanged):</b>\n{route_str}\n\n"
            f"💡 <i>(Tap /setstops anytime if you ever want to change stops)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Active days saved!\n\n"
        "<b>Step 4 of 5:</b> Where do you <b>START</b> your morning journey?\n"
        "Type your station or bus stop name (e.g. <code>DSNR</code>, <code>Miyapur</code>, <code>Kukatpally</code>)\n"
        "<i>Or drop a location pin 📍 using the attachment icon!</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )
    return STATE_ORIGIN_SEARCH


# --- ORIGIN STOP HANDLERS (SEARCH -> PICK -> CONFIRM/RE-ENTER) ---

async def setup_origin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        loc = update.message.location
        stop_dict = {
            "stop_name": "Home / Origin Pin",
            "mode": "place",
            "lat": loc.latitude,
            "lng": loc.longitude,
            "metro_line": None,
            "alert_distance_m": 500,
            "display_title": f"📍 Pinned Location ({loc.latitude:.4f}, {loc.longitude:.4f})",
            "subtitle": "Custom GPS Pin"
        }
        context.user_data["pending_stop"] = stop_dict
        keyboard = [
            [InlineKeyboardButton("✅ Confirm Stop", callback_data="confirm_origin_yes")],
            [InlineKeyboardButton("🔄 Re-enter / Drop Pin Again", callback_data="confirm_origin_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"📍 <b>Confirm Origin Stop:</b>\n\n"
            f"Selected: <b>{stop_dict['display_title']}</b>\n\n"
            f"Is this correct?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_ORIGIN_CONFIRM

    query = update.message.text.strip()
    results = geocoder.search_locations(query, limit=5)

    if not results:
        await update.message.reply_text(
            f"🔍 No locations found matching '{query}'.\nPlease try typing again (e.g. 'Dilsukhnagar' or 'DSNR Metro'):"
        )
        return STATE_ORIGIN_SEARCH

    context.user_data["search_results"] = results
    keyboard = []
    for idx, r in enumerate(results):
        keyboard.append([InlineKeyboardButton(f"{idx + 1}. {r['display_title']}", callback_data=f"pick_origin_{idx}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔍 Found {len(results)} matches for '{query}'.\n<b>Select your Origin stop:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_ORIGIN_PICK


async def setup_origin_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[-1])
    selected = context.user_data["search_results"][idx]

    stop_dict = {
        "stop_name": selected["name"],
        "mode": selected["mode"],
        "lat": selected["lat"],
        "lng": selected["lng"],
        "metro_line": selected.get("metro_line"),
        "alert_distance_m": 800 if selected["mode"] == "metro" else 500,
        "display_title": selected["display_title"],
        "subtitle": selected.get("subtitle", "")
    }
    context.user_data["pending_stop"] = stop_dict

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Stop", callback_data="confirm_origin_yes")],
        [InlineKeyboardButton("🔄 Re-enter / Search Again", callback_data="confirm_origin_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📍 <b>Confirm Origin Stop:</b>\n\n"
        f"Selected: <b>{selected['display_title']}</b>\n"
        f"Area: <i>{selected['subtitle']}</i>\n\n"
        f"Is this correct?",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_ORIGIN_CONFIRM


async def setup_origin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data.split("_")[-1]

    if choice == "yes":
        pending = context.user_data.pop("pending_stop", None)
        setup_data = context.user_data.setdefault("setup", {"stops": []})
        if pending:
            setup_data["stops"].append(pending)

        await query.edit_message_text(
            f"✅ <b>Origin set:</b> {pending['display_title'] if pending else 'Confirmed'}",
            parse_mode=ParseMode.HTML
        )
        return await prompt_mid_stops(query, context, is_callback=True)
    else:
        context.user_data.pop("pending_stop", None)
        await query.edit_message_text(
            "🔄 <b>Let's re-enter your Origin Stop:</b>\n\n"
            "Type your station or bus stop name again (e.g. <code>DSNR</code>, <code>Miyapur</code>)\n"
            "<i>Or drop a location pin 📍 using the attachment icon!</i>",
            parse_mode=ParseMode.HTML
        )
        return STATE_ORIGIN_SEARCH


# --- MID-STOP HANDLERS (SEARCH -> PICK -> CONFIRM/RE-ENTER -> UNDO) ---

async def prompt_mid_stops(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
    keyboard = [
        [InlineKeyboardButton("➕ Add Interchange / Mid-Stop", callback_data="add_mid_stop")],
        [InlineKeyboardButton("⏭️ No Mid-Stops (Direct Route)", callback_data="skip_mid_stop")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "🔄 <b>Interchanges & Mid-Stops:</b>\n"
        "Do you have any transfer stops along the way? (e.g. <b>Ameerpet</b> interchange or a bus stop)\n\n"
        "<i>(I will notify you 1 stop before each interchange so you can deboard!)</i>"
    )

    if is_callback:
        await update_or_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    return STATE_MID_CHOICE


async def setup_mid_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "add_mid_stop":
        await query.edit_message_text(
            "Type the name of your interchange / mid-stop (e.g. <code>Ameerpet</code>):",
            parse_mode=ParseMode.HTML
        )
        return STATE_MID_SEARCH
    elif query.data == "remove_last_stop":
        setup_data = context.user_data.setdefault("setup", {"stops": []})
        if len(setup_data["stops"]) > 1:
            removed = setup_data["stops"].pop()
            route_preview = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in setup_data["stops"]])
            keyboard = [
                [InlineKeyboardButton("➕ Add Interchange / Mid-Stop", callback_data="add_mid_stop")],
                [InlineKeyboardButton("🏁 Proceed to Destination", callback_data="skip_mid_stop")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"🗑️ Removed <b>{removed['stop_name']}</b>!\n\n"
                f"🛣️ <b>Current Route:</b>\n{route_preview}\n\n"
                f"What would you like to do next?",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return STATE_MID_CHOICE
        else:
            await query.answer("Cannot remove the origin stop! Tap /setstops to restart.", show_alert=True)
            return STATE_MID_CHOICE
    else:
        await query.edit_message_text(
            "🎯 <b>Final Step:</b> Where is your <b>Office Destination</b>?\n"
            "Type station or location name (e.g. <code>HITEC City</code>, <code>Mindspace</code>, <code>Raidurg</code>):",
            parse_mode=ParseMode.HTML
        )
        return STATE_DEST_SEARCH


async def setup_mid_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    results = geocoder.search_locations(query, limit=5)

    if not results:
        await update.message.reply_text(
            f"🔍 No locations found for '{query}'. Try typing again (e.g. 'Ameerpet'):"
        )
        return STATE_MID_SEARCH

    context.user_data["search_results"] = results
    keyboard = []
    for idx, r in enumerate(results):
        keyboard.append([InlineKeyboardButton(f"{idx + 1}. {r['display_title']}", callback_data=f"pick_mid_{idx}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔍 Select your <b>Interchange / Mid-Stop:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_MID_PICK


async def setup_mid_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[-1])
    selected = context.user_data["search_results"][idx]

    stop_dict = {
        "stop_name": selected["name"],
        "mode": selected["mode"],
        "lat": selected["lat"],
        "lng": selected["lng"],
        "metro_line": selected.get("metro_line"),
        "alert_distance_m": 800 if selected["mode"] == "metro" else 500,
        "display_title": selected["display_title"],
        "subtitle": selected.get("subtitle", "")
    }
    context.user_data["pending_stop"] = stop_dict

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Mid-Stop", callback_data="confirm_mid_yes")],
        [InlineKeyboardButton("🔄 Re-enter / Search Again", callback_data="confirm_mid_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔄 <b>Confirm Mid-Stop / Interchange:</b>\n\n"
        f"Selected: <b>{selected['display_title']}</b>\n"
        f"Area: <i>{selected['subtitle']}</i>\n\n"
        f"Is this correct?",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_MID_CONFIRM


async def setup_mid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data.split("_")[-1]

    if choice == "yes":
        pending = context.user_data.pop("pending_stop", None)
        setup_data = context.user_data.setdefault("setup", {"stops": []})
        if pending:
            setup_data["stops"].append(pending)

        stops = setup_data.get("stops", [])
        route_preview = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in stops])

        keyboard = [
            [InlineKeyboardButton("➕ Add Another Mid-Stop", callback_data="add_mid_stop")],
            [InlineKeyboardButton("🗑️ Remove This Mid-Stop", callback_data="remove_last_stop")],
            [InlineKeyboardButton("🏁 Proceed to Destination", callback_data="skip_mid_stop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ <b>Mid-Stop Added:</b> {pending['display_title'] if pending else 'Confirmed'}\n\n"
            f"🛣️ <b>Current Route:</b>\n{route_preview}\n\n"
            f"Would you like to add another stop, undo this stop, or proceed to destination?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_MID_CHOICE
    else:
        context.user_data.pop("pending_stop", None)
        await query.edit_message_text(
            "🔄 <b>Let's re-enter your Mid-Stop:</b>\n\n"
            "Type the name of your interchange / mid-stop again (e.g. <code>Ameerpet</code>):",
            parse_mode=ParseMode.HTML
        )
        return STATE_MID_SEARCH


# --- DESTINATION HANDLERS (SEARCH -> PICK -> CONFIRM/RE-ENTER) ---

async def setup_dest_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        loc = update.message.location
        stop_dict = {
            "stop_name": "Office / Destination Pin",
            "mode": "place",
            "lat": loc.latitude,
            "lng": loc.longitude,
            "metro_line": None,
            "alert_distance_m": 500,
            "display_title": f"📍 Pinned Location ({loc.latitude:.4f}, {loc.longitude:.4f})",
            "subtitle": "Custom GPS Pin"
        }
        context.user_data["pending_stop"] = stop_dict

        setup_data = context.user_data.setdefault("setup", {"stops": []})
        preview_stops = setup_data["stops"] + [stop_dict]
        route_preview = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in preview_stops])

        keyboard = [
            [InlineKeyboardButton("✅ Confirm & Save Commute", callback_data="confirm_dest_yes")],
            [InlineKeyboardButton("🔄 Re-enter / Drop Pin Again", callback_data="confirm_dest_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎯 <b>Confirm Final Destination:</b>\n\n"
            f"Selected: <b>{stop_dict['display_title']}</b>\n\n"
            f"🛣️ <b>Complete Commute Preview:</b>\n{route_preview}\n\n"
            f"Save this commute?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        return STATE_DEST_CONFIRM

    query = update.message.text.strip()
    results = geocoder.search_locations(query, limit=5)

    if not results:
        await update.message.reply_text(
            f"🔍 No locations found for '{query}'. Try typing again (e.g. 'HITEC City'):"
        )
        return STATE_DEST_SEARCH

    context.user_data["search_results"] = results
    keyboard = []
    for idx, r in enumerate(results):
        keyboard.append([InlineKeyboardButton(f"{idx + 1}. {r['display_title']}", callback_data=f"pick_dest_{idx}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔍 Select your <b>Final Destination:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_DEST_PICK


async def setup_dest_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[-1])
    selected = context.user_data["search_results"][idx]

    stop_dict = {
        "stop_name": selected["name"],
        "mode": selected["mode"],
        "lat": selected["lat"],
        "lng": selected["lng"],
        "metro_line": selected.get("metro_line"),
        "alert_distance_m": 800 if selected["mode"] == "metro" else 500,
        "display_title": selected["display_title"],
        "subtitle": selected.get("subtitle", "")
    }
    context.user_data["pending_stop"] = stop_dict

    setup_data = context.user_data.setdefault("setup", {"stops": []})
    preview_stops = setup_data["stops"] + [stop_dict]
    route_preview = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in preview_stops])

    keyboard = [
        [InlineKeyboardButton("✅ Confirm & Save Commute", callback_data="confirm_dest_yes")],
        [InlineKeyboardButton("🔄 Re-enter Destination", callback_data="confirm_dest_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🎯 <b>Confirm Final Destination:</b>\n\n"
        f"Selected: <b>{selected['display_title']}</b>\n"
        f"Area: <i>{selected['subtitle']}</i>\n\n"
        f"🛣️ <b>Complete Commute Preview:</b>\n{route_preview}\n\n"
        f"Save this commute?",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )
    return STATE_DEST_CONFIRM


async def setup_dest_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data.split("_")[-1]

    if choice == "yes":
        pending = context.user_data.pop("pending_stop", None)
        setup_data = context.user_data.setdefault("setup", {"stops": []})
        if pending:
            setup_data["stops"].append(pending)

        return await finish_setup(query, context, query.from_user.id, is_callback=True)
    else:
        context.user_data.pop("pending_stop", None)
        await query.edit_message_text(
            "🔄 <b>Let's re-enter your Final Destination:</b>\n\n"
            "Type station or location name again (e.g. <code>HITEC City</code>, <code>Mindspace</code>, <code>Raidurg</code>):",
            parse_mode=ParseMode.HTML
        )
        return STATE_DEST_SEARCH


# --- FINISH SETUP ---

async def finish_setup(update_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int, is_callback: bool = False):
    data = context.user_data.get("setup", {})
    m_time = data.get("morning_time", "08:00")
    e_time = data.get("evening_time", "18:30")
    days = data.get("active_days", "mon,tue,wed,thu,fri")
    stops = data.get("stops", [])

    if not stops:
        stops = [
            {"stop_name": "Dilsukhnagar", "mode": "metro", "lat": 17.3688, "lng": 78.5247, "metro_line": "red", "alert_distance_m": 800},
            {"stop_name": "Ameerpet", "mode": "metro", "lat": 17.4375, "lng": 78.4482, "metro_line": "red", "alert_distance_m": 800},
            {"stop_name": "HITEC City", "mode": "metro", "lat": 17.4474, "lng": 78.3762, "metro_line": "blue", "alert_distance_m": 800}
        ]

    database.update_user_schedule(user_id, m_time, e_time, days)
    database.save_user_route(user_id, "morning", stops)
    database.auto_generate_evening_route(user_id)
    scheduler.schedule_user_commute(context.bot, user_id, lambda u, d: send_commute_prompt(context.bot, u, d))

    context.user_data.pop("setup", None)
    context.user_data.pop("search_results", None)
    context.user_data.pop("pending_stop", None)

    route_str = " ➔ ".join([f"<b>{s['stop_name']}</b>" for s in stops])

    success_text = (
        f"🎉 <b>Commute Saved Successfully!</b>\n\n"
        f"⏰ <b>Schedule:</b>\n"
        f"• Morning: <b>{format_time_12h(m_time)}</b> ({days.upper()})\n"
        f"• Evening: <b>{format_time_12h(e_time)}</b> ({days.upper()})\n\n"
        f"🛣️ <b>Morning Route:</b>\n{route_str}\n\n"
        f"🔄 <i>Evening route is automatically set in reverse!</i>\n\n"
        f"⚡ <b>What happens next:</b>\n"
        f"Every weekday at {format_time_12h(m_time)}, you'll receive the <b>Start / WFH / Leave / Snooze</b> options.\n"
        f"When you start, share your live location once and enjoy your ride!\n\n"
        f"💡 Tap /test to test your commute prompt right now!"
    )

    if is_callback:
        await update_or_query.message.reply_text(success_text, parse_mode=ParseMode.HTML)
    else:
        await update_or_query.message.reply_text(success_text, parse_mode=ParseMode.HTML)

    return ConversationHandler.END


async def setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("setup", None)
    context.user_data.pop("search_results", None)
    context.user_data.pop("pending_stop", None)
    await update.message.reply_text("❌ Setup cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# =====================================================================
# MAIN BOT INITIALIZATION
# =====================================================================

async def post_init(application: Application):
    await scheduler.init_scheduler(application.bot, lambda u, d: send_commute_prompt(application.bot, u, d))
    logger.info("APScheduler initialized in post_init hook.")
    try:
        await application.bot.set_my_commands([
            BotCommand("settime", "Change morning & evening alert timings"),
            BotCommand("setstops", "Change or re-enter travel stops"),
            BotCommand("setup", "Commute settings menu"),
            BotCommand("myroute", "View your saved routes & schedule"),
            BotCommand("test", "Test live commute prompt now"),
            BotCommand("start", "Welcome message & bot guide"),
            BotCommand("cancel", "Cancel current setup")
        ])
        logger.info("Telegram bot commands registered successfully.")
    except Exception as e:
        logger.warning(f"Could not register bot commands: {e}")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Responds to cloud container health checks (Render, Koyeb, Railway, etc.)"""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>TravelNotifier Bot is Running 24/7!</h1><p>Status: Healthy & Active</p>")

    def log_message(self, format, *args):
        pass  # Suppress periodic health-check ping logs from terminal


def start_health_server():
    """Starts a lightweight health check server if PORT or SPACE_ID is set (Cloud PaaS / Hugging Face)."""
    port_str = os.getenv("PORT") or (os.getenv("PORT", "7860") if os.getenv("SPACE_ID") else None)
    if not port_str:
        return
    try:
        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info(f"Cloud health-check HTTP server started on port {port}")
    except Exception as e:
        logger.warning(f"Could not start health-check server: {e}")


def main():
    logger.info("Starting TravelNotifier Telegram Bot with Confirmation & Re-enter flow...")
    start_health_server()

    persistence = PicklePersistence(filepath="bot_state.pickle")

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    # /setup, /settime & /setstops Conversation Handler with Confirmations
    setup_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setup", setup_start),
            CommandHandler("settime", setup_start_time_direct),
            CommandHandler("setstops", setup_start_stops_direct)
        ],
        states={
            STATE_SETUP_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_choice)],
            STATE_MORNING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_morning_time)],
            STATE_EVENING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_evening_time)],
            STATE_ACTIVE_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_active_days)],
            STATE_ORIGIN_SEARCH: [
                MessageHandler(filters.LOCATION, setup_origin_search),
                MessageHandler(filters.TEXT & ~filters.COMMAND, setup_origin_search)
            ],
            STATE_ORIGIN_PICK: [CallbackQueryHandler(setup_origin_pick, pattern=r"^pick_origin_\d+$")],
            STATE_ORIGIN_CONFIRM: [CallbackQueryHandler(setup_origin_confirm, pattern=r"^confirm_origin_(yes|no)$")],
            STATE_MID_CHOICE: [CallbackQueryHandler(setup_mid_choice, pattern=r"^(add_mid_stop|skip_mid_stop|remove_last_stop)$")],
            STATE_MID_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_mid_search)],
            STATE_MID_PICK: [CallbackQueryHandler(setup_mid_pick, pattern=r"^pick_mid_\d+$")],
            STATE_MID_CONFIRM: [CallbackQueryHandler(setup_mid_confirm, pattern=r"^confirm_mid_(yes|no)$")],
            STATE_DEST_SEARCH: [
                MessageHandler(filters.LOCATION, setup_dest_search),
                MessageHandler(filters.TEXT & ~filters.COMMAND, setup_dest_search)
            ],
            STATE_DEST_PICK: [CallbackQueryHandler(setup_dest_pick, pattern=r"^pick_dest_\d+$")],
            STATE_DEST_CONFIRM: [CallbackQueryHandler(setup_dest_confirm, pattern=r"^confirm_dest_(yes|no)$")],
        },
        fallbacks=[CommandHandler("cancel", setup_cancel)],
        allow_reentry=True,
        persistent=True,
        name="setup_conversation"
    )

    application.add_handler(setup_conv)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("myroute", cmd_myroute))
    application.add_handler(CommandHandler("test", cmd_test))
    application.add_handler(CommandHandler("commute", cmd_test))
    application.add_handler(CallbackQueryHandler(on_button_click, pattern=r"^journey_"))

    # Live location handlers
    application.add_handler(MessageHandler(filters.LOCATION, on_location_update))
    application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.LOCATION, on_location_update))

    # Catch-all text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))

    logger.info("Bot is polling for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
