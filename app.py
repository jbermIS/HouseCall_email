import os
import hmac
import hashlib
import json
from flask import Flask, request
import logging
import requests
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
HOUSECALL_SIGNING_SECRET = os.environ.get('HOUSECALL_SIGNING_SECRET', '')
JOB_CHAT_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL', '')
ESTIMATE_CHAT_WEBHOOK_URL = os.environ.get('ESTIMATE_CHAT_WEBHOOK_URL', '')

def format_time(time_str):
    """Format schedule time to be more readable"""
    if not time_str:
        return 'Not scheduled'
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
        logger.info(f"Processing event type: {event}")
        
        # Handle different event types
        if event == 'estimate.scheduled':
            process_estimate_scheduled(payload)
        elif event == 'job.created':
            process_job_created(payload)
        elif event.startswith('job.appointment.'):
            process_appointment_event(event, payload)
            
        return 'OK', 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return 'Error processing request', 500

def process_estimate_scheduled(payload):
    """Handle scheduled estimate events"""
    estimate = payload.get('estimate', {})
    customer = estimate.get('customer', {})
    address = estimate.get('address', {})
    schedule = estimate.get('schedule', {})
    
    message = {
        "cardsV2": [{
            "cardId": f"estimate-{estimate.get('id', 'unknown')}",
            "card": {
                "header": {
                    "title": "New Estimate Scheduled",
                    "subtitle": f"Estimate #{estimate.get('estimate_number', 'N/A')}"
                },
                "sections": [
                    {
                        "header": "Schedule Details",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"Start: {format_time(schedule.get('scheduled_start'))}",
                                    "startIcon": {"knownIcon": "CLOCK"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": f"End: {format_time(schedule.get('scheduled_end'))}",
                                    "startIcon": {"knownIcon": "SCHEDULE"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": f"Arrival Window: {schedule.get('arrival_window', 0)} minutes",
                                    "startIcon": {"knownIcon": "TIMER"}
                                }
                            }
                        ]
                    },
                    {
                        "header": "Customer Information",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"{customer.get('first_name', '')} {customer.get('last_name', '')}",
                                    "startIcon": {"knownIcon": "PERSON"},
                                    "bottomLabel": customer.get('company', 'No company')
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": customer.get('email', 'No email provided'),
                                    "startIcon": {"knownIcon": "EMAIL"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": customer.get('mobile_number', customer.get('home_number', 'No phone provided')),
                                    "startIcon": {"knownIcon": "PHONE"}
                                }
                            }
                        ]
                    },
                    {
                        "header": "Location",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"{address.get('street', '')}, {address.get('street_line_2', '')} {address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}",
                                    "startIcon": {"knownIcon": "LOCATION_ON"},
                                    "bottomLabel": address.get('type', 'service')
                                }
                            }
                        ]
                    }
                ]
            }
        }]
    }

    # Add assigned employees if present
    assigned_employees = estimate.get('assigned_employees', [])
    if assigned_employees:
        employee_widgets = []
        for emp in assigned_employees:
            employee_widgets.append({
                "decoratedText": {
                    "text": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                    "startIcon": {"knownIcon": "PERSON"},
                    "bottomLabel": emp.get('mobile_number', 'No phone provided')
                }
            })
        message["cardsV2"][0]["card"]["sections"].append({
            "header": "Assigned Employees",
            "widgets": employee_widgets
        })

    send_chat_message(message, ESTIMATE_CHAT_WEBHOOK_URL)

def process_job_created(payload):
    """Handle new job creation events"""
    job = payload.get('job', {})
    customer = job.get('customer', {})
    address = job.get('address', {})
    job_type = job.get('job_fields', {}).get('job_type', {})
    
    message = {
        "cardsV2": [{
            "cardId": f"job-{job.get('id', 'unknown')}",
            "card": {
                "header": {
                    "title": "New Job Created",
                    "subtitle": f"Invoice #{job.get('invoice_number', 'N/A')}"
                },
                "sections": [
                    {
                        "header": "Job Details",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": job.get('description', 'No description'),
                                    "startIcon": {"knownIcon": "DESCRIPTION"},
                                    "bottomLabel": f"Type: {job_type.get('name', 'Not specified')}"
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": f"Status: {job.get('work_status', 'Unknown')}",
                                    "startIcon": {"knownIcon": "EVENT_AVAILABLE"}
                                }
                            }
                        ]
                    },
                    {
                        "header": "Customer Information",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"{customer.get('first_name', '')} {customer.get('last_name', '')}",
                                    "startIcon": {"knownIcon": "PERSON"},
                                    "bottomLabel": customer.get('company', 'No company')
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": customer.get('email', 'No email provided'),
                                    "startIcon": {"knownIcon": "EMAIL"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": customer.get('mobile_number', customer.get('home_number', 'No phone provided')),
                                    "startIcon": {"knownIcon": "PHONE"}
                                }
                            }
                        ]
                    },
                    {
                        "header": "Location",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"{address.get('street', '')}, {address.get('street_line_2', '')} {address.get('city', '')}, {address.get('state', '')} {address.get('zip', '')}",
                                    "startIcon": {"knownIcon": "LOCATION_ON"},
                                    "bottomLabel": address.get('type', 'service')
                                }
                            }
                        ]
                    }
                ]
            }
        }]
    }

    # Add notes if present
    notes = job.get('notes', [])
    if notes:
        notes_widgets = []
        for note in notes:
            notes_widgets.append({
                "decoratedText": {
                    "text": note.get('content', ''),
                    "startIcon": {"knownIcon": "DESCRIPTION"}
                }
            })
        message["cardsV2"][0]["card"]["sections"].append({
            "header": "Notes",
            "widgets": notes_widgets
        })

    send_chat_message(message, JOB_CHAT_WEBHOOK_URL)

def process_appointment_event(event_type, payload):
    """Process different types of appointment events"""
    appointment = payload.get('appointment', {})
    
    title_map = {
        'job.appointment.scheduled': ("New Appointment Scheduled", "🆕 New appointment scheduled"),
        'job.appointment.rescheduled': ("Appointment Rescheduled", "📅 Appointment time changed"),
        'job.appointment.appointment_discarded': ("Appointment Cancelled", "❌ Appointment has been cancelled"),
        'job.appointment.appointment_pros_assigned': ("Technicians Assigned", "👨‍🔧 New technicians assigned to appointment"),
        'job.appointment.appointment_pros_unassigned': ("Technicians Removed", "🔄 Technicians removed from appointment")
    }
    
    title, subtitle = title_map.get(event_type, ("Appointment Update", "📝 Appointment updated"))
    is_cancelled = event_type == 'job.appointment.appointment_discarded'
    
    message = {
        "cardsV2": [{
            "cardId": f"appointment-{appointment.get('id', 'unknown')}",
            "card": {
                "header": {
                    "title": title,
                    "subtitle": subtitle
                },
                "sections": [
                    {
                        "header": "Appointment Details",
                        "widgets": [
                            {
                                "decoratedText": {
                                    "text": f"Start: {format_time(appointment.get('start_time'))}",
                                    "startIcon": {"knownIcon": "CLOCK"}
                                }
                            },
                            {
                                "decoratedText": {
                                    "text": f"End: {format_time(appointment.get('end_time'))}",
                                    "startIcon": {"knownIcon": "SCHEDULE"}
                                }
                            }
                        ]
                    }
                ]
            }
        }]
    }

    # Add arrival window if present
    arrival_window = appointment.get('arrival_window_minutes')
    if arrival_window:
        hours = arrival_window // 60
        minutes = arrival_window % 60
        window_text = []
        if hours:
            window_text.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            window_text.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        
        message["cardsV2"][0]["card"]["sections"][0]["widgets"].append({
            "decoratedText": {
                "text": f"Arrival Window: {' and '.join(window_text)}",
                "startIcon": {"knownIcon": "TIMER"}
            }
        })

    # Add technicians section if there are any assigned and it's not cancelled
    dispatched_employees = appointment.get('dispatched_employees', [])
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

    # Add job ID reference
    message["cardsV2"][0]["card"]["sections"].append({
        "widgets": [{
            "decoratedText": {
                "text": f"Job ID: {appointment.get('job_id', 'Unknown')}",
                "startIcon": {"knownIcon": "BOOKMARK"}
            }
        }]
    })

    # Add cancellation notice if applicable
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

    send_chat_message(message, JOB_CHAT_WEBHOOK_URL)

def send_chat_message(message, webhook_url):
    """Send message to specified Google Chat webhook"""
    try:
        response = requests.post(
            webhook_url,
            json=message
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to send message to Google Chat: {response.text}")
            raise Exception(f"Failed to send to Google Chat: {response.text}")
        else:
            logger.info(f"Successfully sent message to chat: {webhook_url}")
            
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        raise
