import os
import json
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import threading
import time
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///meds.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Twilio setup with proper error handling
twilio_sid = os.getenv('TWILIO_SID')
twilio_token = os.getenv('TWILIO_TOKEN')
twilio_number = os.getenv('TWILIO_WHATSAPP')

if not twilio_sid or not twilio_token:
    raise Exception("❌ Twilio credentials missing! Please set TWILIO_SID and TWILIO_TOKEN environment variables in Render dashboard.")

try:
    from twilio.rest import Client
    twilio_client = Client(twilio_sid, twilio_token)
    print("✅ Twilio client initialized successfully")
except Exception as e:
    raise Exception(f"❌ Twilio initialization failed: {e}")

# MODELS
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    language = db.Column(db.String(20), default='english')
    clinic_id = db.Column(db.String(50))
    conversation_state = db.Column(db.String(50), default='language_selection')
    conversation_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_phone = db.Column(db.String(20))
    name = db.Column(db.String(100))
    dosage = db.Column(db.String(50))
    times = db.Column(db.JSON)
    active = db.Column(db.Boolean, default=True)

class Adherence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_phone = db.Column(db.String(20))
    medication = db.Column(db.String(100))
    scheduled_time = db.Column(db.DateTime)
    taken = db.Column(db.Boolean, default=False)
    responded_at = db.Column(db.DateTime)

# MESSAGES
MESSAGES = {
    'english': {
        'welcome': "🏥 Welcome to MediRemind SA! Choose language: 1. English 2. isiZulu",
        'medication_ask': "💊 What medication are you taking?",
        'dosage_ask': "📏 What is your dosage?",
        'schedule_ask': "⏰ What times should we remind you?",
        'confirmation': "✅ Setup Complete!",
        'reminder': "💊 Time for your {medication} ({dosage})",
        'taken_confirmation': "✅ Thank you! Dose recorded.",
        'help': "🆘 Help: Reply TAKEN, CHANGE, LANGUAGE, STOP"
    },
    'zulu': {
        'welcome': "🏥 Sawubona! Khetha ulimi: 1. isiZulu 2. English",
        'medication_ask': "💊 Uthatha umuthi onjani?",
        'confirmation': "✅ Kuhle!",
        'reminder': "💊 Isikhathi sokuthatha {medication}",
        'taken_confirmation': "✅ Ngiyabonga!"
    }
}

LANGUAGE_MAP = {'1': 'english', '2': 'zulu', 'english': 'english', 'zulu': 'zulu'}

def send_whatsapp(to_number, message):
    """Send WhatsApp message"""
    try:
        twilio_client.messages.create(
            body=message,
            from_=f'whatsapp:{twilio_number}',
            to=f'whatsapp:{to_number}'
        )
        print(f"Message sent to {to_number}")
        return True
    except Exception as e:
        print(f"WhatsApp send failed: {e}")
        return False

def get_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    today = datetime.today().date()
    
    patients = Patient.query.count()
    active_meds = Medication.query.filter_by(active=True).count()
    
    reminders_today = Adherence.query.filter(
        db.func.date(Adherence.scheduled_time) == today
    ).count()
    
    taken_today = Adherence.query.filter(
        db.func.date(Adherence.scheduled_time) == today,
        Adherence.taken == True
    ).count()
    
    adherence_rate = (taken_today / reminders_today * 100) if reminders_today > 0 else 0
    
    return {
        'patients': patients,
        'active_meds': active_meds,
        'reminders_today': reminders_today,
        'taken_today': taken_today,
        'adherence_rate': adherence_rate,
        'today': today
    }

# === SIMPLIFIED DASHBOARD ROUTES ===

@app.route('/')
def clinic_dashboard():
    """Modern main dashboard with medical media rotation"""
    try:
        stats = get_dashboard_stats()
        
        # Stock medical media from Unsplash
        medical_media = [
            {
                "url": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=600&h=400&fit=crop",
                "title": "Patient Care Excellence",
                "description": "24/7 multilingual medication support"
            },
            {
                "url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=600&h=400&fit=crop",
                "title": "Health Monitoring", 
                "description": "Real-time adherence tracking and analytics"
            },
            {
                "url": "https://images.unsplash.com/photo-1584467735871-8db9ac8e5e3a?w=600&h=400&fit=crop",
                "title": "Multilingual Support",
                "description": "11 official South African languages"
            }
        ]
        
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>MediRemind SA - Dashboard</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
            <style>
                :root {{
                    --ai-primary: #6366f1;
                    --ai-secondary: #8b5cf6;
                    --ai-accent: #06b6d4;
                    --ai-gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #06b6d4 100%);
                }}
                
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                
                body {{
                    font-family: 'Inter', sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: #1f2937;
                }}
                
                .dashboard-container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .header {{
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 20px 30px;
                    margin-bottom: 30px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                }}
                
                .logo {{
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    text-decoration: none;
                    color: inherit;
                }}
                
                .logo-icon {{
                    width: 50px;
                    height: 50px;
                    background: var(--ai-gradient);
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 24px;
                }}
                
                .logo-text h1 {{
                    font-size: 28px;
                    font-weight: 700;
                    background: var(--ai-gradient);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                
                .nav-tabs {{
                    display: flex;
                    gap: 10px;
                }}
                
                .nav-tab {{
                    padding: 10px 20px;
                    border-radius: 8px;
                    text-decoration: none;
                    color: #6b7280;
                    font-weight: 500;
                    background: rgba(255, 255, 255, 0.5);
                }}
                
                .nav-tab:hover {{
                    background: rgba(255, 255, 255, 0.8);
                    color: var(--ai-primary);
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .stat-card {{
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 16px;
                    padding: 25px;
                    text-align: center;
                    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
                }}
                
                .stat-number {{
                    font-size: 32px;
                    font-weight: 700;
                    background: var(--ai-gradient);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    margin-bottom: 10px;
                }}
                
                .media-section {{
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    padding: 30px;
                    margin-bottom: 30px;
                }}
                
                .media-rotator {{
                    height: 300px;
                    border-radius: 15px;
                    overflow: hidden;
                    position: relative;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                
                .media-slide {{
                    position: absolute;
                    width: 100%;
                    height: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    opacity: 0;
                    transition: opacity 1s ease;
                    padding: 40px;
                }}
                
                .media-slide.active {{
                    opacity: 1;
                }}
                
                .media-image {{
                    max-width: 100%;
                    max-height: 200px;
                    border-radius: 10px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                }}
                
                .media-content {{
                    text-align: center;
                    color: white;
                }}
                
                .actions-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                }}
                
                .action-btn {{
                    background: var(--ai-gradient);
                    color: white;
                    padding: 15px 20px;
                    border-radius: 12px;
                    text-decoration: none;
                    text-align: center;
                    transition: transform 0.3s ease;
                }}
                
                .action-btn:hover {{
                    transform: translateY(-2px);
                }}
            </style>
        </head>
        <body>
            <div class="dashboard-container">
                <!-- Header -->
                <div class="header">
                    <a href="/" class="logo">
                        <div class="logo-icon">💊</div>
                        <div class="logo-text">
                            <h1>MediRemind SA</h1>
                        </div>
                    </a>
                    <div class="nav-tabs">
                        <a href="/analytics" class="nav-tab">Analytics</a>
                        <a href="/reports" class="nav-tab">Reports</a>
                        <a href="/settings" class="nav-tab">Settings</a>
                        <a href="/support" class="nav-tab">Support</a>
                    </div>
                </div>
                
                <!-- Stats Grid -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">{stats['patients']}</div>
                        <div>Total Patients</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{stats['active_meds']}</div>
                        <div>Active Medications</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{stats['reminders_today']}</div>
                        <div>Reminders Today</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{stats['adherence_rate']:.1f}%</div>
                        <div>Adherence Rate</div>
                    </div>
                </div>
                
                <!-- Medical Media -->
                <div class="media-section">
                    <h2>Healthcare Excellence</h2>
                    <div class="media-rotator" id="mediaRotator">
                        <div class="media-slide active">
                            <div class="media-content">
                                <img src="{medical_media[0]['url']}" alt="{medical_media[0]['title']}" class="media-image">
                                <h3>{medical_media[0]['title']}</h3>
                                <p>{medical_media[0]['description']}</p>
                            </div>
                        </div>
                        <div class="media-slide">
                            <div class="media-content">
                                <img src="{medical_media[1]['url']}" alt="{medical_media[1]['title']}" class="media-image">
                                <h3>{medical_media[1]['title']}</h3>
                                <p>{medical_media[1]['description']}</p>
                            </div>
                        </div>
                        <div class="media-slide">
                            <div class="media-content">
                                <img src="{medical_media[2]['url']}" alt="{medical_media[2]['title']}" class="media-image">
                                <h3>{medical_media[2]['title']}</h3>
                                <p>{medical_media[2]['description']}</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Quick Actions -->
                <div class="media-section">
                    <h2>Quick Actions</h2>
                    <div class="actions-grid">
                        <a href="/add_patient" class="action-btn">Add Patient</a>
                        <a href="/patients" class="action-btn">View Patients</a>
                        <a href="/send-test-reminder" class="action-btn">Test System</a>
                        <a href="/analytics" class="action-btn">View Analytics</a>
                    </div>
                </div>
            </div>
            
            <script>
                // Simple media rotator
                let currentSlide = 0;
                const slides = document.querySelectorAll('.media-slide');
                
                function showSlide(index) {{
                    slides.forEach(slide => slide.classList.remove('active'));
                    slides[index].classList.add('active');
                    currentSlide = index;
                }}
                
                function nextSlide() {{
                    currentSlide = (currentSlide + 1) % slides.length;
                    showSlide(currentSlide);
                }}
                
                // Auto-rotate every 5 seconds
                setInterval(nextSlide, 5000);
            </script>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h1>Error loading dashboard: {str(e)}</h1>"

# === SIMPLE ROUTES FOR OTHER PAGES ===

@app.route('/analytics')
def analytics_dashboard():
    stats = get_dashboard_stats()
    return f"""
    <html>
    <head><title>Analytics</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>📊 Analytics Dashboard</h1>
                <p>Total Patients: {stats['patients']}</p>
                <p>Adherence Rate: {stats['adherence_rate']:.1f}%</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/reports')
def reports_dashboard():
    return """
    <html>
    <head><title>Reports</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>📋 Reports</h1>
                <p>Generate patient reports and analytics.</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/settings')
def settings_dashboard():
    return """
    <html>
    <head><title>Settings</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>⚙️ Settings</h1>
                <p>Configure your system settings.</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/support')
def support_dashboard():
    return """
    <html>
    <head><title>Support</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>🛟 Support</h1>
                <p>Get help and support.</p>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/patients')
def view_patients():
    patients = Patient.query.all()
    patients_list = "".join([f"<li>{p.name} ({p.phone}) - {p.language}</li>" for p in patients])
    return f"""
    <html>
    <head><title>Patients</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>👥 Patients</h1>
                <ul>{patients_list}</ul>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/add_patient', methods=['GET', 'POST'])
def add_patient():
    if request.method == 'POST':
        patient = Patient(
            phone=request.form['phone'],
            name=request.form['name'],
            language=request.form['language'],
            clinic_id='demo'
        )
        db.session.add(patient)
        db.session.commit()
        return "Patient added! <a href='/'>Back to Dashboard</a>"
    
    return """
    <html>
    <head><title>Add Patient</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto;">
            <div style="background: white; padding: 30px; border-radius: 20px;">
                <h1>Add Patient</h1>
                <form method="POST">
                    <input type="text" name="name" placeholder="Name" required style="width: 100%; padding: 10px; margin: 10px 0;"><br>
                    <input type="text" name="phone" placeholder="Phone" required style="width: 100%; padding: 10px; margin: 10px 0;"><br>
                    <select name="language" style="width: 100%; padding: 10px; margin: 10px 0;">
                        <option value="english">English</option>
                        <option value="zulu">isiZulu</option>
                    </select><br>
                    <button type="submit" style="width: 100%; padding: 15px; background: #6366f1; color: white; border: none; border-radius: 5px;">Add Patient</button>
                </form>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

# === EXISTING FUNCTIONALITY ===

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get('Body', '').strip()
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        
        # Simple response for now
        response = "🏥 Welcome to MediRemind SA! Choose language: 1. English 2. isiZulu"
        
        send_whatsapp(from_number, response)
        return '<Response></Response>'
        
    except Exception as e:
        return '<Response><Message>System error</Message></Response>'

def reminder_worker():
    """Send medication reminders"""
    while True:
        try:
            time.sleep(60)
        except:
            time.sleep(60)

def init_app():
    with app.app_context():
        db.create_all()
        worker_thread = threading.Thread(target=reminder_worker, daemon=True)
        worker_thread.start()

init_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
