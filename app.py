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
    patient_id = db.Column(db.String(20), unique=True)
    phone = db.Column(db.String(20), unique=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    id_number = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    emergency_contact = db.Column(db.String(100))
    emergency_name = db.Column(db.String(100))
    medical_aid = db.Column(db.String(100))
    medical_aid_number = db.Column(db.String(50))
    language = db.Column(db.String(20), default='english')
    allergies = db.Column(db.Text)
    chronic_conditions = db.Column(db.Text)
    blood_type = db.Column(db.String(5))
    clinic_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    name = db.Column(db.String(100))
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(50))  # daily, weekly, etc.
    instructions = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    prescribed_by = db.Column(db.String(100))
    times = db.Column(db.JSON)
    active = db.Column(db.Boolean, default=True)

class Adherence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    medication_id = db.Column(db.Integer, db.ForeignKey('medication.id'))
    scheduled_time = db.Column(db.DateTime)
    taken = db.Column(db.Boolean, default=False)
    responded_at = db.Column(db.DateTime)

# Complete 11 Official South African Languages
LANGUAGES = {
    'english': 'English',
    'zulu': 'isiZulu', 
    'xhosa': 'isiXhosa',
    'afrikaans': 'Afrikaans',
    'sotho': 'Sesotho',
    'tswana': 'Setswana',
    'tsonga': 'Xitsonga', 
    'swati': 'siSwati',
    'venda': 'Tshivenda',
    'ndebele': 'isiNdebele',
    'pedi': 'Sepedi'
}

# MESSAGES
MESSAGES = {
    'english': {
        'welcome': "🏥 Welcome to MediRemind SA! Choose language: 1. English 2. isiZulu",
        'medication_ask': "💊 What medication are you taking?",
        'confirmation': "✅ Setup Complete!",
        'reminder': "💊 Time for your {medication} ({dosage})",
    }
}

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

def generate_patient_id():
    """Generate unique patient ID"""
    year = datetime.now().year
    last_patient = Patient.query.order_by(Patient.id.desc()).first()
    last_id = last_patient.id if last_patient else 0
    return f"MW{year}{str(last_id + 1).zfill(4)}"

# === DASHBOARD ROUTES ===

@app.route('/')
def clinic_dashboard():
    """Modern main dashboard with medical media rotation"""
    try:
        stats = get_dashboard_stats()
        
        # Stock medical media from Unsplash
        medical_media = [
            {
                "url": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&h=400&fit=crop",
                "title": "Patient Care Excellence",
                "description": "24/7 multilingual medication support across South Africa"
            },
            {
                "url": "https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=800&h=400&fit=crop", 
                "title": "Health Monitoring", 
                "description": "Real-time adherence tracking and advanced analytics"
            },
            {
                "url": "https://images.unsplash.com/photo-1584467735871-8db9ac8e5e3a?w=800&h=400&fit=crop",
                "title": "Multilingual Support",
                "description": "Full support for all 11 official South African languages"
            },
            {
                "url": "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=800&h=400&fit=crop",
                "title": "AI-Powered Reminders",
                "description": "Smart WhatsApp conversations for better patient outcomes"
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
                    transition: all 0.3s ease;
                }}
                
                .nav-tab:hover {{
                    background: rgba(255, 255, 255, 0.8);
                    color: var(--ai-primary);
                    transform: translateY(-2px);
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
                    transition: transform 0.3s ease;
                }}
                
                .stat-card:hover {{
                    transform: translateY(-5px);
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
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                }}
                
                .media-rotator {{
                    height: 400px;
                    border-radius: 15px;
                    overflow: hidden;
                    position: relative;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    margin: 20px 0;
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
                }}
                
                .media-slide.active {{
                    opacity: 1;
                }}
                
                .media-image {{
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }}
                
                .media-content {{
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    background: linear-gradient(transparent, rgba(0,0,0,0.8));
                    color: white;
                    padding: 40px;
                    text-align: center;
                }}
                
                .media-title {{
                    font-size: 28px;
                    font-weight: 600;
                    margin-bottom: 10px;
                }}
                
                .media-description {{
                    font-size: 18px;
                    opacity: 0.9;
                }}
                
                .media-controls {{
                    display: flex;
                    justify-content: center;
                    gap: 10px;
                    margin-top: 20px;
                }}
                
                .media-dot {{
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background: rgba(255,255,255,0.3);
                    cursor: pointer;
                    transition: all 0.3s ease;
                }}
                
                .media-dot.active {{
                    background: white;
                    transform: scale(1.2);
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
                    font-weight: 500;
                }}
                
                .action-btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 10px 25px rgba(99,102,241,0.3);
                }}
                
                .form-group {{
                    margin-bottom: 20px;
                }}
                
                .form-label {{
                    display: block;
                    margin-bottom: 5px;
                    font-weight: 500;
                    color: #374151;
                }}
                
                .form-input {{
                    width: 100%;
                    padding: 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    font-size: 16px;
                }}
                
                .form-select {{
                    width: 100%;
                    padding: 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    font-size: 16px;
                    background: white;
                }}
                
                .form-textarea {{
                    width: 100%;
                    padding: 12px;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                    font-size: 16px;
                    min-height: 80px;
                    resize: vertical;
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
                    <h2 style="margin-bottom: 20px;">🏥 Healthcare Excellence</h2>
                    <div class="media-rotator" id="mediaRotator">
                        {"".join([f'''
                        <div class="media-slide {'active' if i == 0 else ''}">
                            <img src="{media['url']}" alt="{media['title']}" class="media-image">
                            <div class="media-content">
                                <div class="media-title">{media['title']}</div>
                                <div class="media-description">{media['description']}</div>
                            </div>
                        </div>
                        ''' for i, media in enumerate(medical_media)])}
                    </div>
                    <div class="media-controls" id="mediaControls">
                        {"".join([f'<div class="media-dot {'active' if i == 0 else ''}" data-slide="{i}"></div>' for i in range(len(medical_media))])}
                    </div>
                </div>
                
                <!-- Quick Actions -->
                <div class="media-section">
                    <h2 style="margin-bottom: 20px;">⚡ Quick Actions</h2>
                    <div class="actions-grid">
                        <a href="/add_patient" class="action-btn">
                            <i class="fas fa-user-plus"></i> Add New Patient
                        </a>
                        <a href="/patients" class="action-btn">
                            <i class="fas fa-search"></i> View All Patients
                        </a>
                        <a href="/send-test-reminder" class="action-btn">
                            <i class="fas fa-bell"></i> Test System
                        </a>
                        <a href="/analytics" class="action-btn">
                            <i class="fas fa-chart-bar"></i> View Analytics
                        </a>
                    </div>
                </div>
            </div>
            
            <script>
                // Enhanced media rotator
                let currentSlide = 0;
                const slides = document.querySelectorAll('.media-slide');
                const dots = document.querySelectorAll('.media-dot');
                const totalSlides = slides.length;
                
                function showSlide(index) {{
                    // Hide all slides
                    slides.forEach(slide => slide.classList.remove('active'));
                    dots.forEach(dot => dot.classList.remove('active'));
                    
                    // Show current slide
                    slides[index].classList.add('active');
                    dots[index].classList.add('active');
                    currentSlide = index;
                }}
                
                function nextSlide() {{
                    currentSlide = (currentSlide + 1) % totalSlides;
                    showSlide(currentSlide);
                }}
                
                // Add click events to dots
                dots.forEach((dot, index) => {{
                    dot.addEventListener('click', () => showSlide(index));
                }});
                
                // Auto-rotate every 5 seconds
                setInterval(nextSlide, 5000);
                
                // Pause on hover
                const rotator = document.getElementById('mediaRotator');
                let rotateInterval = setInterval(nextSlide, 5000);
                
                rotator.addEventListener('mouseenter', () => clearInterval(rotateInterval));
                rotator.addEventListener('mouseleave', () => {{
                    clearInterval(rotateInterval);
                    rotateInterval = setInterval(nextSlide, 5000);
                }});
            </script>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h1>Error loading dashboard: {str(e)}</h1>"

# === COMPREHENSIVE PATIENT FORM ===

@app.route('/add_patient', methods=['GET', 'POST'])
def add_patient():
    if request.method == 'POST':
        try:
            # Generate patient ID
            patient_id = generate_patient_id()
            
            # Create patient record
            patient = Patient(
                patient_id=patient_id,
                first_name=request.form['first_name'],
                last_name=request.form['last_name'],
                phone=request.form['phone'],
                id_number=request.form.get('id_number'),
                date_of_birth=datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d') if request.form.get('date_of_birth') else None,
                gender=request.form.get('gender'),
                address=request.form.get('address'),
                emergency_contact=request.form.get('emergency_contact'),
                emergency_name=request.form.get('emergency_name'),
                medical_aid=request.form.get('medical_aid'),
                medical_aid_number=request.form.get('medical_aid_number'),
                language=request.form.get('language', 'english'),
                allergies=request.form.get('allergies'),
                chronic_conditions=request.form.get('chronic_conditions'),
                blood_type=request.form.get('blood_type'),
                clinic_id='demo'
            )
            
            db.session.add(patient)
            db.session.commit()
            
            # Add medication if provided
            medication_name = request.form.get('medication_name')
            if medication_name:
                medication = Medication(
                    patient_id=patient.id,
                    name=medication_name,
                    dosage=request.form.get('dosage'),
                    frequency=request.form.get('frequency'),
                    instructions=request.form.get('instructions'),
                    prescribed_by=request.form.get('prescribed_by'),
                    times=request.form.get('reminder_times', '').split(','),
                    start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d') if request.form.get('start_date') else None
                )
                db.session.add(medication)
                db.session.commit()
            
            return f'''
            <div style="max-width: 500px; margin: 50px auto; padding: 30px; background: white; border-radius: 15px; text-align: center;">
                <h2 style="color: #10b981;">✅ Patient Added Successfully!</h2>
                <p><strong>Patient ID:</strong> {patient_id}</p>
                <p><strong>Name:</strong> {patient.first_name} {patient.last_name}</p>
                <p><strong>Phone:</strong> {patient.phone}</p>
                <div style="margin-top: 30px;">
                    <a href="/add_patient" style="background: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-right: 10px;">Add Another Patient</a>
                    <a href="/" style="background: #6b7280; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none;">Back to Dashboard</a>
                </div>
            </div>
            '''
            
        except Exception as e:
            return f"<h2>Error adding patient: {str(e)}</h2><a href='/add_patient'>Try Again</a>"
    
    # Generate language options
    language_options = "".join([f'<option value="{code}">{name}</option>' for code, name in LANGUAGES.items()])
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Add Patient - MediRemind SA</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            body {{
                font-family: 'Inter', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                margin: 0;
                padding: 20px;
            }}
            
            .form-container {{
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            }}
            
            .form-header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            
            .form-header h1 {{
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 32px;
                margin-bottom: 10px;
            }}
            
            .form-section {{
                margin-bottom: 30px;
                padding: 25px;
                background: #f8fafc;
                border-radius: 12px;
                border-left: 4px solid #6366f1;
            }}
            
            .form-section h3 {{
                color: #6366f1;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            
            .form-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }}
            
            .form-group {{
                margin-bottom: 20px;
            }}
            
            .form-label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #374151;
                font-size: 14px;
            }}
            
            .form-input, .form-select, .form-textarea {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                font-size: 16px;
                transition: border-color 0.3s ease;
            }}
            
            .form-input:focus, .form-select:focus, .form-textarea:focus {{
                outline: none;
                border-color: #6366f1;
            }}
            
            .form-textarea {{
                min-height: 80px;
                resize: vertical;
            }}
            
            .submit-btn {{
                width: 100%;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                color: white;
                padding: 16px;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.3s ease;
            }}
            
            .submit-btn:hover {{
                transform: translateY(-2px);
            }}
            
            .back-link {{
                display: inline-block;
                margin-top: 20px;
                color: #6366f1;
                text-decoration: none;
                font-weight: 500;
            }}
        </style>
    </head>
    <body>
        <div class="form-container">
            <div class="form-header">
                <h1><i class="fas fa-user-plus"></i> Add New Patient</h1>
                <p>Complete patient profile for comprehensive care management</p>
            </div>
            
            <form method="POST">
                <!-- Personal Information -->
                <div class="form-section">
                    <h3><i class="fas fa-user"></i> Personal Information</h3>
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label">First Name *</label>
                            <input type="text" name="first_name" class="form-input" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Last Name *</label>
                            <input type="text" name="last_name" class="form-input" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Phone Number *</label>
                            <input type="tel" name="phone" class="form-input" placeholder="27821234567" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">ID Number</label>
                            <input type="text" name="id_number" class="form-input" placeholder="Optional">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Date of Birth</label>
                            <input type="date" name="date_of_birth" class="form-input">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Gender</label>
                            <select name="gender" class="form-select">
                                <option value="">Select Gender</option>
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                    </div>
                </div>
                
                <!-- Contact & Emergency -->
                <div class="form-section">
                    <h3><i class="fas fa-address-book"></i> Contact & Emergency Information</h3>
                    <div class="form-group">
                        <label class="form-label">Home Address</label>
                        <textarea name="address" class="form-textarea" placeholder="Full residential address"></textarea>
                    </div>
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label">Emergency Contact Number</label>
                            <input type="tel" name="emergency_contact" class="form-input" placeholder="27820000000">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Emergency Contact Name</label>
                            <input type="text" name="emergency_name" class="form-input" placeholder="Full name">
                        </div>
                    </div>
                </div>
                
                <!-- Medical Information -->
                <div class="form-section">
                    <h3><i class="fas fa-heartbeat"></i> Medical Information</h3>
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label">Medical Aid</label>
                            <input type="text" name="medical_aid" class="form-input" placeholder="Medical aid provider">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Medical Aid Number</label>
                            <input type="text" name="medical_aid_number" class="form-input" placeholder="Membership number">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Blood Type</label>
                            <select name="blood_type" class="form-select">
                                <option value="">Unknown</option>
                                <option value="A+">A+</option>
                                <option value="A-">A-</option>
                                <option value="B+">B+</option>
                                <option value="B-">B-</option>
                                <option value="AB+">AB+</option>
                                <option value="AB-">AB-</option>
                                <option value="O+">O+</option>
                                <option value="O-">O-</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Preferred Language *</label>
                            <select name="language" class="form-select" required>
                                <option value="english">English</option>
                                {language_options.replace('<option value="english">English</option>', '')}
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Allergies</label>
                        <textarea name="allergies" class="form-textarea" placeholder="List any known allergies"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Chronic Conditions</label>
                        <textarea name="chronic_conditions" class="form-textarea" placeholder="Any ongoing medical conditions"></textarea>
                    </div>
                </div>
                
                <!-- Medication Information -->
                <div class="form-section">
                    <h3><i class="fas fa-pills"></i> Medication Information (Optional)</h3>
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label">Medication Name</label>
                            <input type="text" name="medication_name" class="form-input" placeholder="e.g., Metformin, ARVs">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Dosage</label>
                            <input type="text" name="dosage" class="form-input" placeholder="e.g., 500mg, 1 tablet">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Frequency</label>
                            <select name="frequency" class="form-select">
                                <option value="">Select frequency</option>
                                <option value="daily">Daily</option>
                                <option value="twice_daily">Twice Daily</option>
                                <option value="weekly">Weekly</option>
                                <option value="monthly">Monthly</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Prescribed By</label>
                            <input type="text" name="prescribed_by" class="form-input" placeholder="Doctor's name">
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Special Instructions</label>
                        <textarea name="instructions" class="form-textarea" placeholder="Any special instructions for this medication"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Reminder Times (comma separated)</label>
                        <input type="text" name="reminder_times" class="form-input" placeholder="e.g., 08:00,20:00">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Start Date</label>
                        <input type="date" name="start_date" class="form-input">
                    </div>
                </div>
                
                <button type="submit" class="submit-btn">
                    <i class="fas fa-save"></i> Save Patient Profile
                </button>
            </form>
            
            <a href="/" class="back-link">
                <i class="fas fa-arrow-left"></i> Back to Dashboard
            </a>
        </div>
    </body>
    </html>
    '''

# ... (rest of the routes remain the same as previous version)

@app.route('/patients')
def view_patients():
    patients = Patient.query.all()
    patients_list = "".join([f"<tr><td>{p.patient_id}</td><td>{p.first_name} {p.last_name}</td><td>{p.phone}</td><td>{p.language}</td></tr>" for p in patients])
    return f"""
    <html>
    <head><title>Patients</title></head>
    <body style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px;">
        <div style="max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 20px;">
            <h1>👥 Patients ({len(patients)})</h1>
            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                <tr style="background: #f8fafc;">
                    <th style="padding: 12px; text-align: left;">Patient ID</th>
                    <th style="padding: 12px; text-align: left;">Name</th>
                    <th style="padding: 12px; text-align: left;">Phone</th>
                    <th style="padding: 12px; text-align: left;">Language</th>
                </tr>
                {patients_list}
            </table>
            <a href="/" style="display: inline-block; margin-top: 20px; padding: 10px 20px; background: #6366f1; color: white; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a>
        </div>
    </body>
    </html>
    """

# ... (other routes: analytics, reports, settings, support remain the same)

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get('Body', '').strip()
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        
        response = "🏥 Welcome to MediRemind SA! Choose language: 1. English 2. isiZulu"
        
        send_whatsapp(from_number, response)
        return '<Response></Response>'
        
    except Exception as e:
        return '<Response><Message>System error</Message></Response>'

def reminder_worker():
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
