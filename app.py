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

# === DASHBOARD ROUTES ===

@app.route('/')
def clinic_dashboard():
    """Modern main dashboard with medical media rotation"""
    stats = get_dashboard_stats()
    
    # Stock medical media from Unsplash
    medical_media = [
        {
            "type": "image", 
            "url": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=600&h=400&fit=crop",
            "title": "Patient Care Excellence",
            "description": "24/7 multilingual medication support"
        },
        {
            "type": "image", 
            "url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=600&h=400&fit=crop",
            "title": "Health Monitoring",
            "description": "Real-time adherence tracking and analytics"
        },
        {
            "type": "image", 
            "url": "https://images.unsplash.com/photo-1584467735871-8db9ac8e5e3a?w=600&h=400&fit=crop",
            "title": "Multilingual Support",
            "description": "11 official South African languages"
        },
        {
            "type": "image", 
            "url": "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=600&h=400&fit=crop",
            "title": "AI-Powered Reminders",
            "description": "Smart WhatsApp conversations"
        }
    ]
    
    return render_dashboard_template('dashboard', stats=stats, medical_media=medical_media)

@app.route('/analytics')
def analytics_dashboard():
    """Advanced analytics page"""
    stats = get_dashboard_stats()
    language_stats = db.session.query(Patient.language, func.count(Patient.id)).group_by(Patient.language).all()
    adherence_data = get_adherence_analytics()
    
    return render_dashboard_template('analytics', stats=stats, 
                                   language_stats=language_stats,
                                   adherence_data=adherence_data)

@app.route('/reports')
def reports_dashboard():
    """Reports generation page"""
    stats = get_dashboard_stats()
    return render_dashboard_template('reports', stats=stats)

@app.route('/settings')
def settings_dashboard():
    """System settings page"""
    stats = get_dashboard_stats()
    return render_dashboard_template('settings', stats=stats)

@app.route('/support')
def support_dashboard():
    """Support and help page"""
    stats = get_dashboard_stats()
    return render_dashboard_template('support', stats=stats)

@app.route('/patients')
def view_patients():
    """Patients management page"""
    patients = Patient.query.all()
    stats = get_dashboard_stats()
    return render_dashboard_template('patients', stats=stats, patients=patients)

@app.route('/send-test-reminder')
def send_test_reminder():
    """Test system functionality"""
    stats = get_dashboard_stats()
    return render_dashboard_template('test_reminder', stats=stats, 
                                   message="Test reminder functionality ready!")

@app.route('/add_patient', methods=['GET', 'POST'])
def add_patient():
    """Add new patient page"""
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
        
        welcome_msg = MESSAGES[patient.language]['confirmation']
        send_whatsapp(patient.phone, welcome_msg)
        
        return "Patient added successfully!"
    
    stats = get_dashboard_stats()
    return render_dashboard_template('add_patient', stats=stats)

# === WHATSAPP WEBHOOK ===

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get('Body', '').strip()
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        
        print(f"Message from {from_number}: {incoming_msg}")
        
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
            'date': date.strftime('%b %d'),
            'rate': rate,
            'reminders': day_reminders,
            'taken': day_taken
        })
    return adherence_data

def render_dashboard_template(page, **kwargs):
    """Render modern dashboard templates"""
    stats = kwargs.get('stats', {})
    medical_media = kwargs.get('medical_media', [])
    
    base_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>MediRemind SA - {page.title()}</title>
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
                text-decoration: none;
                color: inherit;
            }}
            
            .logo:hover {{ text-decoration: none; color: inherit; }}
            
            .logo-icon {{
                width: 50px; height: 50px; background: var(--ai-gradient); border-radius: 12px;
                display: flex; align-items: center; justify-content: center; color: white;
                font-size: 24px; font-weight: bold;
            }}
            
            .logo-text h1 {{
                font-size: 28px; font-weight: 700; background: var(--ai-gradient);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
            }}
            
            .logo-text p {{ font-size: 14px; color: #6b7280; font-weight: 500; }}
            
            .nav-tabs {{
                display: flex; gap: 5px; background: rgba(255, 255, 255, 0.1);
                padding: 5px; border-radius: 12px; backdrop-filter: blur(10px);
            }}
            
            .nav-tab {{
                padding: 10px 20px; border-radius: 8px; text-decoration: none; color: #6b7280;
                font-weight: 500; transition: all 0.3s ease; background: transparent;
            }}
            
            .nav-tab.active, .nav-tab:hover {{
                background: rgba(255, 255, 255, 0.9); color: var(--ai-primary);
            }}
            
            .content-card {{
                background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
                border-radius: 20px; padding: 30px; margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            
            .stats-grid {{
                display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px; margin-bottom: 30px;
            }}
            
            .stat-card {{
                background: rgba(255, 255, 255, 0.9); border-radius: 16px; padding: 20px;
                text-align: center; border: 1px solid rgba(255, 255, 255, 0.3);
                transition: transform 0.3s ease;
            }}
            
            .stat-card:hover {{ transform: translateY(-5px); }}
            
            .stat-number {{
                font-size: 32px; font-weight: 700; background: var(--ai-gradient);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }}
            
            /* Media Rotator Styles */
            .media-rotator {{
                position: relative; height: 300px; border-radius: 15px; overflow: hidden;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 20px 0;
            }}
            
            .media-slide {{
                position: absolute; top: 0; left: 0; width: 100%; height: 100%;
                opacity: 0; transition: opacity 1s ease-in-out;
                display: flex; align-items: center; justify-content: center; padding: 40px;
            }}
            
            .media-slide.active {{ opacity: 1; }}
            
            .media-content {{ text-align: center; color: white; }}
            
            .media-image {{ max-width: 100%; max-height: 200px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }}
            
            .media-title {{ font-size: 24px; font-weight: 600; margin: 15px 0 10px 0; }}
            
            .media-description {{ font-size: 16px; opacity: 0.9; }}
            
            .media-controls {{ display: flex; justify-content: center; gap: 10px; margin-top: 20px; }}
            
            .media-dot {{ width: 12px; height: 12px; border-radius: 50%; background: rgba(255,255,255,0.3); cursor: pointer; transition: all 0.3s ease; }}
            
            .media-dot.active {{ background: white; transform: scale(1.2); }}
            
            .actions-grid {{
                display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px; margin-top: 20px;
            }}
            
            .action-btn {{
                background: var(--ai-gradient); color: white; padding: 15px 20px;
                border-radius: 12px; text-decoration: none; text-align: center;
                transition: all 0.3s ease; display: block;
            }}
            
            .action-btn:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px rgba(99,102,241,0.3); color: white; }}
        </style>
    </head>
    <body>
        <div class="dashboard-container">
            <div class="header">
                <a href="/" class="logo">
                    <div class="logo-icon">💊</div>
                    <div class="logo-text">
                        <h1>MediRemind SA</h1>
                        <small>AI-Powered Medication Adherence</small>
                    </div>
                </a>
                <div class="nav-tabs">
                    <a href="/analytics" class="nav-tab {'active' if page == 'analytics' else ''}">📊 Analytics</a>
                    <a href="/reports" class="nav-tab {'active' if page == 'reports' else ''}">📋 Reports</a>
                    <a href="/settings" class="nav-tab {'active' if page == 'settings' else ''}">⚙️ Settings</a>
                    <a href="/support" class="nav-tab {'active' if page == 'support' else ''}">🛟 Support</a>
                </div>
            </div>
            {get_page_content(page, stats, **kwargs)}
        </div>
        <script>{get_page_script(page, medical_media)}</script>
    </body>
    </html>
    """
    
    return base_html

def get_page_content(page, stats, **kwargs):
    """Get content for each page"""
    if page == 'dashboard':
        medical_media = kwargs.get('medical_media', [])
        media_html = ""
        if medical_media:
            media_html = f"""
            <div class="content-card">
                <h2><i class="fas fa-images"></i> Healthcare Excellence</h2>
                <div class="media-rotator" id="mediaRotator"></div>
            </div>
            """
        
        return f"""
        <div class="stats-grid">
            <div class="stat-card"><div class="stat-number">{stats['patients']}</div><div>Total Patients</div></div>
            <div class="stat-card"><div class="stat-number">{stats['active_meds']}</div><div>Active Medications</div></div>
            <div class="stat-card"><div class="stat-number">{stats['reminders_today']}</div><div>Reminders Today</div></div>
            <div class="stat-card"><div class="stat-number">{stats['adherence_rate']:.1f}%</div><div>Adherence Rate</div></div>
        </div>
        {media_html}
        <div class="content-card">
            <h2><i class="fas fa-bolt"></i> Quick Actions</h2>
            <div class="actions-grid">
                <a href="/add_patient" class="action-btn"><i class="fas fa-user-plus"></i> Add Patient</a>
                <a href="/patients" class="action-btn"><i class="fas fa-list"></i> View Patients</a>
                <a href="/send-test-reminder" class="action-btn"><i class="fas fa-bell"></i> Test System</a>
                <a href="/analytics" class="action-btn"><i class="fas fa-chart-bar"></i> View Analytics</a>
            </div>
        </div>
        """
    
    elif page == 'analytics':
        language_stats = kwargs.get('language_stats', [])
        adherence_data = kwargs.get('adherence_data', [])
        
        lang_html = "".join([f"<div style='padding: 10px; border-bottom: 1px solid #eee;'>{lang[0]}: <strong>{lang[1]}</strong> patients</div>" for lang in language_stats])
        adherence_html = "".join([f"<div style='padding: 10px; border-bottom: 1px solid #eee;'>{item['date']}: <strong>{item['rate']:.1f}%</strong> ({item['taken']}/{item['reminders']})</div>" for item in adherence_data])
        
        return f"""
        <div class="content-card">
            <h2>📊 Analytics Dashboard</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 20px;">
                <div>
                    <h3>Language Distribution</h3>
                    {lang_html}
                </div>
                <div>
                    <h3>Adherence Trends</h3>
                    {adherence_html}
                </div>
            </div>
        </div>
        """
    
    elif page == 'reports':
        return """
        <div class="content-card">
            <h2>📋 Reports Generator</h2>
            <p>Generate detailed reports for your clinic:</p>
            <div class="actions-grid">
                <a href="#" class="action-btn"><i class="fas fa-file-medical"></i> Patient Adherence Report</a>
                <a href="#" class="action-btn"><i class="fas fa-chart-bar"></i> Monthly Analytics</a>
                <a href="#" class="action-btn"><i class="fas fa-language"></i> Language Usage Report</a>
                <a href="#" class="action-btn"><i class="fas fa-download"></i> Export All Data</a>
            </div>
        </div>
        """
    
    elif page == 'settings':
        return """
        <div class="content-card">
            <h2>⚙️ System Settings</h2>
            <p>Configure your MediRemind SA system:</p>
            <div style="display: grid; gap: 15px; max-width: 500px;">
                <div style="padding: 15px; background: #f8fafc; border-radius: 10px;">
                    <strong>WhatsApp Settings</strong><br>
                    <small>Configure your Twilio integration</small>
                </div>
                <div style="padding: 15px; background: #f8fafc; border-radius: 10px;">
                    <strong>Clinic Information</strong><br>
                    <small>Update your clinic details</small>
                </div>
                <div style="padding: 15px; background: #f8fafc; border-radius: 10px;">
                    <strong>Reminder Schedule</strong><br>
                    <small>Set default reminder times</small>
                </div>
            </div>
        </div>
        """
    
    elif page == 'support':
        return """
        <div class="content-card">
            <h2>🛟 Support & Help</h2>
            <p>Get help with MediRemind SA:</p>
            <div class="actions-grid">
                <a href="#" class="action-btn"><i class="fas fa-book"></i> User Guide</a>
                <a href="#" class="action-btn"><i class="fas fa-video"></i> Video Tutorials</a>
                <a href="#" class="action-btn"><i class="fas fa-envelope"></i> Contact Support</a>
                <a href="#" class="action-btn"><i class="fas fa-bug"></i> Report Issue</a>
            </div>
        </div>
        """
    
    elif page == 'patients':
        patients = kwargs.get('patients', [])
        patients_html = "".join([f"<div style='padding: 15px; border-bottom: 1px solid #eee;'><strong>{p.name}</strong> ({p.phone}) - {p.language}</div>" for p in patients]) if patients else "<p>No patients yet.</p>"
        return f"""
        <div class="content-card">
            <h2>👥 Patients Management</h2>
            <div style="margin-top: 20px;">
                {patients_html}
            </div>
        </div>
        """
    
    elif page == 'add_patient':
        return """
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
        return f"""
        <div class="content-card">
            <h2>🔧 System Test</h2>
            <p style="margin-top: 20px; padding: 20px; background: #10b98120; border-radius: 10px; border-left: 4px solid #10b981;">
                {message}
            </p>
        </div>
        """

def get_page_script(page, medical_media):
    """Get JavaScript for each page"""
    if page == 'dashboard' and medical_media:
        return f"""
        document.addEventListener('DOMContentLoaded', function() {{
            const media = {json.dumps(medical_media)};
            const rotator = document.getElementById('mediaRotator');
            let currentSlide = 0;
            
            // Create slides and controls
            media.forEach((item, index) => {{
                const slide = document.createElement('div');
                slide.className = 'media-slide';
                slide.innerHTML = `
                    <div class="media-content">
                        <img src="${{item.url}}" alt="${{item.title}}" class="media-image">
                        <div class="media-title">${{item.title}}</div>
                        <div class="media-description">${{item.description}}</div>
                    </div>
                `;
                rotator.appendChild(slide);
            }});
            
            const controls = document.createElement('div');
            controls.className = 'media-controls';
            media.forEach((_, index) => {{
                const dot = document.createElement('div');
                dot.className = 'media-dot';
                dot.onclick = () => showSlide(index);
                controls.appendChild(dot);
            }});
            rotator.appendChild(controls);
            
            function showSlide(index) {{
                document.querySelectorAll('.media-slide').forEach(slide => slide.classList.remove('active'));
                document.querySelectorAll('.media-dot').forEach(dot => dot.classList.remove('active'));
                document.querySelectorAll('.media-slide')[index].classList.add('active');
                document.querySelectorAll('.media-dot')[index].classList.add('active');
                currentSlide = index;
            }}
            
            function nextSlide() {{
                currentSlide = (currentSlide + 1) % media.length;
                showSlide(currentSlide);
            }}
            
            // Start rotation
            showSlide(0);
            setInterval(nextSlide, 5000);
        }});
        """
    return ""

# === EXISTING FUNCTIONS ===

def handle_conversation(patient_phone, message):
    """Handle patient conversations"""
    patient = Patient.query.filter_by(phone=patient_phone).first()
    if not patient:
        patient = Patient(phone=patient_phone, conversation_state='language_selection')
        db.session.add(patient)
        db.session.commit()
        return MESSAGES['english']['welcome']
    return MESSAGES[patient.language]['help']

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
                        message = MESSAGES[patient.language]['reminder'].format(medication=med.name, dosage=med.dosage)
                        send_whatsapp(patient.phone, message)
            time.sleep(60)
        except Exception as e:
            print(f"Reminder error: {e}")
            time.sleep(60)

def init_app():
    with app.app_context():
        db.create_all()
        print("Database initialized!")
        worker_thread = threading.Thread(target=reminder_worker, daemon=True)
        worker_thread.start()
        print("Reminder worker started!")

init_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
