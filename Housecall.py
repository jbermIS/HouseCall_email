# app.py
import os
import hmac
import hashlib
import json
import requests
from flask import Flask, request
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get secrets from environment variables
HOUSECALL_SIGNING_SECRET = os.environ.get('HOUSECALL_SIGNING_SECRET')
GOOGLE_CHAT_WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL')

@app.route('/')
def home():
    return 'Webhook receiver is running!'

@app.route('/webhooks/housecall', methods=['POST'])
def handle_webhook():
    if not HOUSECALL_SIGNING_SECRET or not GOOGLE_CHAT_WEBHOOK_URL:
        logger.error("Missing required environment variables")
        return 'Configuration error', 500

    # Log incoming request
    logger.info(f"Received webhook request")
    
    # Get headers
    timestamp = request.headers.get('Api-Timestamp')
    provided_signature = request.headers.get('Api-Signature')
    
    # Get request body
    payload = request.get_json()
    logger.info(f"Received payload for event: {payload.get('event')}")
    
    # Verify webhook signature
    signature_body = f"{timestamp}.{json.dumps(payload)}"
    calculated_signature = hmac.new(
        HOUSECALL_SIGNING_SECRET.encode(),
        signature_body.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(calculated_signature, provided_signature):
        logger.error("Signature verification failed")
        return 'Invalid signature', 401

    # Process verified webhook
    if payload['event'] == 'job.created':
        logger.info("Processing job.created event")
        try:
            send_chat_notification(payload['job'])
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            return 'Error processing webhook', 500
    else:
        logger.info(f"Ignoring non-job.created event: {payload['event']}")
        return 'OK', 200

def send_chat_notification(job):
    customer = job['customer']
    address = job['address']
    schedule = job['schedule']
    
    # Format address if available
    address_str = ''
    if address:
        address_parts = [
            address.get('street'),
            address.get('street_line_2'),
            address.get('city'),
            address.get('state'),
            address.get('zip')
        ]
        address_str = ', '.join(filter(None, address_parts))

    # Format schedule if available
    schedule_str = 'Unscheduled'
    if schedule and schedule.get('scheduled_start'):
        schedule_str = schedule['scheduled_start']

    # Create message card
    message = {
        "cardsV2": [{
            "cardId": f"job-{job.get('id', 'unknown')}",
            "card": {
                "header": {
                    "title": "New Job Created",
                    "subtitle": f"Invoice #{job.get('invoice_number', 'N/A')}"
                },
                "sections": [{
                    "header": "Customer Details",
                    "widgets": [{
                        "decoratedText": {
                            "text": f"{customer['first_name']} {customer['last_name']}",
                            "bottomLabel": customer.get('email', 'No email provided')
                        }
                    }]
                }, {
                    "header": "Job Details",
                    "widgets": [{
                        "decoratedText": {
                            "text": job.get('description', 'No description provided'),
                            "bottomLabel": f"Total Amount: ${job.get('total_amount', 0):,.2f}"
                        }
                    }, {
                        "decoratedText": {
                            "text": address_str,
                            "bottomLabel": f"Scheduled for: {schedule_str}"
                        }
                    }]
                }]
            }
        }]
    }

    # Send to Google Chat
    response = requests.post(
        GOOGLE_CHAT_WEBHOOK_URL,
        json=message
    )
    
    if response.status_code != 200:
        logger.error(f"Failed to send message to Google Chat: {response.text}")
        raise Exception(f"Failed to send to Google Chat: {response.text}")
    else:
        logger.info("Successfully sent message to Google Chat")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)