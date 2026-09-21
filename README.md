# 🚆 TravelNotifier — Commute Autopilot Telegram Bot

An automated, zero-stress daily commute assistant built for Hyderabad and multi-modal transit commuters.

---

## ✨ Features

- ⏰ **Dynamic Daily Prompts**: Wakes up automatically at your scheduled morning & evening times with 4 interactive options:
  - `[ 🚀 Start Journey ]`
  - `[ 🏠 WFH ]`
  - `[ 🏖️ On Leave ]`
  - `[ ⏰ Snooze (+30 mins) ]`
- 🚇 **Metro 1-Stop Advance Warning**: Sequence-aware Hyderabad Metro tracking. Alerts you **1 stop before** your interchange or deboarding station:
  - 📍 Currently approaching/passing: *[Previous Station]*
  - 🚇 Next Stop: *[Target Station / Interchange]*
  - 🎯 Final Destination: *[Destination]*
- 🚌 **Bus Stop 500m Advance Warning**: Geofence alerts fired **500 meters** before your target bus stop.
- 🔄 **Automatic Evening Commute**: Automatically reverses your morning route for the return commute.
- 🔍 **Smart Autocomplete**: Integrates pre-indexed Hyderabad Metro stations + OpenStreetMap/Photon search with transport badges (`🚇 Metro`, `🚌 Bus`, `📍 Landmark`).
- 📍 **Telegram Pin Drop Support**: Users can also drop a location pin directly via Telegram attachment.
- 💬 **Flexible Fallbacks**: Leave late? Just send **"Hi"** to the bot anytime to bring up your commute buttons!

---

## 🚀 Quick Start (Local Setup)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create or edit `.env`:
```env
TELEGRAM_BOT_TOKEN=8809214897:AAFaRs3DdDEjR_8Jb-rtn7PiK60kSuctIDw
TIMEZONE=Asia/Kolkata
DEFAULT_ALERT_DISTANCE_BUS_METERS=500
DEFAULT_ALERT_DISTANCE_METRO_METERS=800
```

### 3. Run Automated Tests
```bash
python test_suite.py
```

### 4. Start the Bot
```bash
python bot.py
```

Open your Telegram and search for `@Travel_Notifier_bot` (or open [t.me/Travel_Notifier_bot](https://t.me/Travel_Notifier_bot)) and send `/start`!

---

## 📱 Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Welcome message & quick actions |
| `/setup` | 5-step interactive setup wizard (Morning/Evening times, Days, Origin, Mid-stops, Dest) |
| `/myroute` | View your saved schedule and morning/evening route details |
| `/test` | Trigger the commute prompt immediately for testing |
| `Hi` / `Hello` | Brings up your commute prompt buttons anytime |

---

## ☁️ Free 24/7 Cloud Deployment (Render / Railway)

### Deploy on Render (Free Background Worker):
1. Push this folder to a GitHub repository.
2. Sign up on [Render.com](https://render.com) (Free).
3. Click **New +** ➔ **Background Worker**.
4. Connect your GitHub repository.
5. Set:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
6. Add Environment Variable:
   - `TELEGRAM_BOT_TOKEN` = `your_token_here`
7. Click **Create Background Worker**. It will now run 24/7 in the cloud!
