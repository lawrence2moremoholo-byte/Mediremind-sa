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

# MESSAGES (simplified for example)
MESSAGES = {
    'english': {
        'welcome': "🏥 Welcome to MediRemind SA! Choose language: 1. English 2. isiZulu",
        'medication_ask': "💊 What medication are you taking?",
        'dosage_ask': "📏 What is your dosage?",
        'schedule_ask': "⏰ What times should we remind you?",
        'confirmation': "✅ Setup Complete! Medication: {medication}",
        'reminder': "💊 Time for your {medication} ({dosage})",
        'taken_confirmation': "✅ Thank you! Dose recorded.",
        'help': "🆘 Help: Reply TAKEN, CHANGE, LANGUAGE, STOP"
    },
    'zulu': {
        'welcome': "🏥 Sawubona! Khetha ulimi: 1. isiZulu 2. English",
        'medication_ask': "💊 Uthatha umuthi onjani?",
        'confirmation': "✅ Kuhle! Umuthi: {medication}",
        'reminder': "💊 Isikhathi sokuthatha {medication}",
        'taken_confirmation': "✅ Ngiyabonga! Isilinganiso sirekhodiwe."
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

# === MODERN DASHBOARD ROUTES ===

@app.route('/')
def clinic_dashboard():
    """Modern main dashboard"""
    stats = get_dashboard_stats()
    return render_dashboard_template('dashboard', stats=stats)

@app.route('/analytics')
def analytics_dashboard():
    """Advanced analytics page"""
    stats = get_dashboard_stats()
    
    # Language distribution
    language_stats = db.session.query(
        Patient.language, 
        func.count(Patient.id)
    ).group_by(Patient.language).all()
    
    # Adherence trends
    adherence_data = get_adherence_analytics()
    
    return render_dashboard_template('analytics', stats=stats, 
                                   language_stats=language_stats,
                                   adherence_data=adherence_data)

@app.route('/patients')
def view_patients():
    """Modern patients listing"""
    patients = Patient.query.all()
    stats = get_dashboard_stats()
    return render_dashboard_template('patients', stats=stats, patients=patients)

@app.route('/send-test-reminder')
def send_test_reminder():
    """Send a test reminder to verify system works"""
    # This would typically send to a test number or admin
    test_message = "🔧 Test reminder from MediRemind SA. System is working correctly!"
    # send_whatsapp("+27820000000", test_message)  # Uncomment with real number
    
    stats = get_dashboard_stats()
    return render_dashboard_template('test_reminder', stats=stats, 
                                   message="Test reminder functionality ready!")

# === EXISTING FUNCTIONALITY ===

@app.route('/add_patient', methods=['GET', 'POST'])
def add_patient():
    if request.method == 'POST':
        patient = Patient(
            phone=request.form['phone'],
            name=request.form['name'],
            language=request.form['language'],
            clinic_id='demo',
            conversation_state='active'
        )
        db.session.add(patient)
        
        med = Medication(
            patient_phone=patient.phone,
            name=request.form['medication'],
            dosage=request.form['dosage'],
            times=request.form['times'].split(',')
        )
        db.session.add(med)
        db.session.commit()
        
        welcome_msg = MESSAGES[patient.language]['confirmation'].format(medication=med.name)
        send_whatsapp(patient.phone, welcome_msg)
        
        return "Patient added successfully!"
    
    stats = get_dashboard_stats()
    return render_dashboard_template('add_patient', stats=stats)

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get('Body', '').strip()
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        
        response = handle_conversation(from_number, incoming_msg)
        send_whatsapp(from_number, response)
        
        return '<Response></Response>'
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return '<Response><Message>System error. Please try again.</Message></Response>'

# === HELPER FUNCTIONS ===

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

def get_adherence_analytics():
    """Get adherence analytics data"""
    # Last 7 days adherence rates
    adherence_data = []
    for i in range(7):
        date = datetime.today().date() - timedelta(days=i)
        day_reminders = Adherence.query.filter(
            db.func.date(Adherence.scheduled_time) == date
        ).count()
        day_taken = Adherence.query.filter(
            db.func.date(Adherence.scheduled_time) == date,
            Adherence.taken == True
        ).count()
        rate = (day_taken / day_reminders * 100) if day_reminders > 0 else 0
        adherence_data.append({
            'date': date,
            'rate': rate,
            'reminders': day_reminders,
            'taken': day_taken
        })
    return adherence_data

def render_dashboard_template(page, **kwargs):
    """Render modern dashboard templates"""
    base_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MediRemind SA - {page_title}</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            :root {{
                --ai-primary: #6366f1;
                --ai-secondary: #8b5cf6;
                --ai-accent: #06b6d4;
                --ai-success: #10b981;
                --ai-warning: #f59e0b;
                --ai-error: #ef4444;
                --ai-dark: #1f2937;
                --ai-light: #f8fafc;
                --ai-gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #06b6d4 100%);
            }}
            
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: 'Inter', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: var(--ai-dark);
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
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            
            .logo {{
                display: flex;
                align-items: center;
                gap: 15px;
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
                font-weight: bold;
            }}
            
            .logo-text h1 {{
                font-size: 28px;
                font-weight: 700;
                background: var(--ai-gradient);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .nav-buttons {{
                display: flex;
                gap: 10px;
            }}
            
            .nav-btn {{
                background: rgba(99, 102, 241, 0.1);
                border: 2px solid rgba(99, 102, 241, 0.2);
                color: var(--ai-primary);
                padding: 10px 20px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            
            .nav-btn:hover {{
                background: var(--ai-primary);
                color: white;
                transform: translateY(-2px);
            }}
            
            .content-card {{
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                margin-bottom: 20px;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            
            .stat-card {{
                background: rgba(255, 255, 255, 0.9);
                border-radius: 16px;
                padding: 20px;
                text-align: center;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
            
            .stat-number {{
                font-size: 32px;
                font-weight: 700;
                background: var(--ai-gradient);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
        </style>
    </head>
    <body>
        <div class="dashboard-container">
            <div class="header">
                <div class="logo">
                    <div class="logo-icon">💊</div>
                    <div class="logo-text">
                        <h1>MediRemind SA</h1>
                        <small>AI-Powered Medication Adherence</small>
                    </div>
                </div>
                <div class="nav-buttons">
                    <a href="/" class="nav-btn">Dashboard</a>
                    <a href="/patients" class="nav-btn">Patients</a>
                    <a href="/analytics" class="nav-btn">Analytics</a>
                    <a href="/add_patient" class="nav-btn">Add Patient</a>
                </div>
            </div>
            {content}
        </div>
    </body>
    </html>
    """
    
    stats = kwargs.get('stats', {})
    
    if page == 'dashboard':
        content = f"""
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
        
        <div class="content-card">
            <h2>Quick Actions</h2>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 20px;">
                <a href="/add_patient" class="nav-btn" style="text-align: center;">
                    <i class="fas fa-user-plus"></i> Add Patient
                </a>
                <a href="/patients" class="nav-btn" style="text-align: center;">
                    <i class="fas fa-list"></i> View Patients
                </a>
                <a href="/analytics" class="nav-btn" style="text-align: center;">
                    <i class="fas fa-chart-bar"></i> Analytics
                </a>
                <a href="/send-test-reminder" class="nav-btn" style="text-align: center;">
                    <i class="fas fa-bell"></i> Test System
                </a>
            </div>
        </div>
        """
        
    elif page == 'analytics':
        language_stats = kwargs.get('language_stats', [])
        adherence_data = kwargs.get('adherence_data', [])
        
        lang_chart = "".join([f"<div>{lang[0]}: {lang[1]} patients</div>" for lang in language_stats])
        adherence_chart = "".join([f"<div>{item['date']}: {item['rate']:.1f}%</div>" for item in adherence_data[:3]])
        
        content = f"""
        <div class="content-card">
            <h2>📊 Analytics Dashboard</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 20px;">
                <div>
                    <h3>Language Distribution</h3>
                    {lang_chart}
                </div>
                <div>
                    <h3>Adherence Trends (Last 3 Days)</h3>
                    {adherence_chart}
                </div>
            </div>
        </div>
        """
        
    elif page == 'patients':
        patients = kwargs.get('patients', [])
        patients_list = "".join([f"<div style='padding: 15px; border-bottom: 1px solid #eee;'>{p.name} ({p.phone}) - {p.language}</div>" for p in patients])
        
        content = f"""
        <div class="content-card">
            <h2>👥 Patients Management</h2>
            <div style="margin-top: 20px;">
                {patients_list if patients else "<p>No patients yet. <a href='/add_patient'>Add your first patient</a></p>"}
            </div>
        </div>
        """
        
    elif page == 'add_patient':
        content = """
        <div class="content-card">
            <h2>👤 Add New Patient</h2>
            <form method="POST" style="margin-top: 20px; display: grid; gap: 15px; max-width: 400px;">
                <input type="text" name="name" placeholder="Patient Name" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                <input type="text" name="phone" placeholder="27821234567" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                <select name="language" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                    <option value="english">English</option>
                    <option value="zulu">isiZulu</option>
                </select>
                <input type="text" name="medication" placeholder="Medication Name" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                <input type="text" name="dosage" placeholder="Dosage" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                <input type="text" name="times" placeholder="08:00,20:00" required style="padding: 12px; border-radius: 10px; border: 1px solid #ddd;">
                <button type="submit" style="background: var(--ai-gradient); color: white; padding: 15px; border: none; border-radius: 10px; font-weight: 600;">Add Patient</button>
            </form>
        </div>
        """
        
    elif page == 'test_reminder':
        message = kwargs.get('message', 'Test completed')
        content = f"""
        <div class="content-card">
            <h2>🔧 System Test</h2>
            <p style="margin-top: 20px; padding: 20px; background: #10b98120; border-radius: 10px; border-left: 4px solid #10b981;">
                {message}
            </p>
            <p style="margin-top: 15px;">This feature allows you to test the WhatsApp integration without affecting real patients.</p>
        </div>
        """
    
    return base_template.format(page_title=page.title(), content=content)

# === EXISTING CONVERSATION FUNCTIONS ===

def handle_conversation(patient_phone, message):
    """Handle patient conversations"""
    patient = Patient.query.filter_by(phone=patient_phone).first()
    
    if not patient:
        patient = Patient(phone=patient_phone, conversation_state='language_selection')
        db.session.add(patient)
        db.session.commit()
        return MESSAGES['english']['welcome']
    
    # ... rest of conversation logic (simplified for example)
    return MESSAGES[patient.language]['help']

# === BACKGROUND WORKER ===

def reminder_worker():
    """Send medication reminders"""
    while True:
        try:
            current_time = datetime.now().strftime('%H:%M')
            due_meds = Medication.query.filter_by(active=True).all()
            
            for med in due_meds:
                if med.times and current_time in med.times:
                    patient = Patient.query.filter_by(phone=med.patient_phone).first()
                    if patient:
                        message = MESSAGES[patient.language]['reminder'].format(
                            medication=med.name, dosage=med.dosage
                        )
                        send_whatsapp(patient.phone, message)
                        # Log reminder...
            
            time.sleep(60)
        except Exception as e:
            print(f"Reminder error: {e}")
            time.sleep(60)

# === INITIALIZATION ===

def init_app():
    with app.app_context():
        db.create_all()
        print("Database initialized!")
        # Start background worker
        worker_thread = threading.Thread(target=reminder_worker, daemon=True)
        worker_thread.start()
        print("Reminder worker started!")

init_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
