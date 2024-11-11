import os
import hmac
import hashlib
import json
from flask import Flask, request
import logging
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get secrets from environment variables
HOUSECALL_SIGNING_SECRET = os.environ.get('HOUSECALL_SIGNING_SECRET', '')
GOOGLE_CHAT_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL', '')

def format_time(time_str):
    """Format schedule time to be more readable"""
    try:
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except:
        return time_str

@app.route('/')
def home():
    return 'Webhook receiver is running!'

@app.route('/webhooks/housecall', methods=['POST'])
def handle_webhook():
    logger.info("\n=== New Webhook Request ===")
    logger.info(f"Headers: {dict(request.headers)}")
    raw_body = request.get_data(as_text=True)
    logger.info(f"Raw Body: {raw_body}")
    
    try:
        payload = json.loads(raw_body)
        event = payload.get('event', '')
        
        if event in [
            'job.appointment.scheduled',
            'job.appointment.rescheduled',
            'job.appointment.appointment_discarded',
            'job.appointment.appointment_pros_assigned',
            'job.appointment.appointment_pros_unassigned'
        ]:
            logger.info(f"Processing {event} event")
            process_appointment_event(event, payload)
            
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return 'Error processing request', 500

def process_appointment_event(event_type, payload):
    """Process different types of appointment events"""
    appointment = payload.get('appointment', {})
    
    # Create appropriate message based on event type
    if event_type == 'job.appointment.scheduled':
        send_appointment_notification(
            "New Appointment Scheduled",
            appointment,
            "🆕 New appointment scheduled"
        )
    
    elif event_type == 'job.appointment.rescheduled':
        send_appointment_notification(
            "Appointment Rescheduled",
            appointment,
            "📅 Appointment time changed"
        )
    
    elif event_type == 'job.appointment.appointment_discarded':
        send_appointment_notification(
            "Appointment Cancelled",
            appointment,
            "❌ Appointment has been cancelled",
            is_cancelled=True
        )
    
    elif event_type == 'job.appointment.appointment_pros_assigned':
        send_appointment_notification(
            "Technicians Assigned",
            appointment,
            "👨‍🔧 New technicians assigned to appointment"
        )
    
    elif event_type == 'job.appointment.appointment_pros_unassigned':
        send_appointment_notification(
            "Technicians Removed",
            appointment,
            "🔄 Technicians removed from appointment"
        )

def send_appointment_notification(title, appointment, subtitle, is_cancelled=False):
    """Send formatted notification to Google Chat"""
    
    job_id = appointment.get('job_id', 'Unknown')
    start_time = format_time(appointment.get('start_time', ''))
    end_time = format_time(appointment.get('end_time', ''))
    arrival_window = appointment.get('arrival_window_minutes', 0)
    dispatched_employees = appointment.get('dispatched_employees', [])

    # Create the card message
    message = {
        "cardsV2": [{
            "cardId": f"appointment-{appointment.get('id', 'unknown')}",
            "card": {
                "header": {
                    "title": title,
                    "subtitle": subtitle,
                    "imageUrl": "https://via.placeholder.com/64",  # Optional: Replace with your logo
                    "imageType": "SQUARE"
                },
                "sections": [
                    {
                        "header": "Appointment Details",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"Start: {start_time}",
                                    "startIcon": {"knownIcon": "CLOCK"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": f"End: {end_time}",
                                    "startIcon": {"knownIcon": "CLOCK"}
                                }
                            }
                        ]
                    }
                ]
            }
        }]
    }

    # Add arrival window if present
    if arrival_window:
        window_hours = arrival_window // 60
        window_minutes = arrival_window % 60
        window_text = ""
        if window_hours:
            window_text += f"{window_hours} hour{'s' if window_hours != 1 else ''}"
        if window_minutes:
            if window_text:
                window_text += " and "
            window_text += f"{window_minutes} minute{'s' if window_minutes != 1 else ''}"
            
        message["cardsV2"][0]["card"]["sections"][0]["widgets"].append({
            "decoratedText": {
                "text": f"Arrival Window: {window_text}",
                "startIcon": {"knownIcon": "SCHEDULE"},
                "bottomLabel": "Customer will be notified within this window"
            }
        })

    # Add technicians section if there are any assigned
    if dispatched_employees and not is_cancelled:
        tech_section = {
            "header": "Assigned Technicians",
            "widgets": []
        }
        
        for emp in dispatched_employees:
            tech_section["widgets"].append({
                "decoratedText": {
                    "text": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                    "startIcon": {"knownIcon": "PERSON"},
                    "bottomLabel": emp.get('mobile_number', 'No phone provided')
                }
            })
            
        message["cardsV2"][0]["card"]["sections"].append(tech_section)

    # If cancelled, add a cancelled section
    if is_cancelled:
        message["cardsV2"][0]["card"]["sections"].append({
            "header": "Cancellation Notice",
            "widgets": [{
                "decoratedText": {
                    "text": "This appointment has been cancelled",
                    "startIcon": {"knownIcon": "CANCEL"},
                    "bottomLabel": "Please update your schedule accordingly"
                }
            }]
        })

    # Add job ID reference
    message["cardsV2"][0]["card"]["sections"].append({
        "widgets": [{
            "decoratedText": {
                "text": f"Job ID: {job_id}",
                "startIcon": {"knownIcon": "BOOKMARK"}
            }
        }]
    })

    # Send to Google Chat
    try:
        response = requests.post(
            GOOGLE_CHAT_WEBHOOK_URL,
            json=message
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to send message to Google Chat: {response.text}")
            raise Exception(f"Failed to send to Google Chat: {response.text}")
        else:
            logger.info("Successfully sent message to Google Chat")
            
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        raise