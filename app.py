"""
Hugging Face Spaces Entrypoint for TravelNotifier
Runs a Gradio status dashboard and launches the Telegram Bot autopilot in a background thread.
"""

import os
import threading
import gradio as gr
import bot


def run_telegram_bot():
    """Runs the Telegram bot polling and APScheduler in a background thread."""
    bot.main()


# Start Telegram bot worker thread
bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
bot_thread.start()


# Gradio UI for Hugging Face Space
with gr.Blocks(title="TravelNotifier Autopilot") as demo:
    gr.Markdown("# 🚆 TravelNotifier — Commute Autopilot")
    gr.Markdown(
        """
        ### 🟢 System Status: Active & Running 24/7
        This Hugging Face Space hosts the **TravelNotifier Telegram Bot** autopilot for multi-modal commuters.

        - ⏰ **Scheduled Morning & Evening Prompts**
        - 🚇 **Metro 1-Stop Advance Alerts**
        - 🚌 **Bus 500m Geofence Deboarding Alerts**
        - 🔄 **Automatic Evening Route Reversal**

        ---
        ### 💬 Connect on Telegram:
        👉 Open Telegram and chat with: **[@Travel_Notifier_bot](https://t.me/Travel_Notifier_bot)**
        """
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")))
