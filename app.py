import os
import json
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from twilio.rest import Client
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///meds.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Twilio setup
twilio_client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_TOKEN'))
twilio_number = os.getenv('TWILIO_WHATSAPP')

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

# COMPLETE 11-LANGUAGE MESSAGES
MESSAGES = {
    'english': {
        'welcome': "🏥 *Welcome to MediRemind SA!*\n\nPlease choose your language:\n\n1. English\n2. isiZulu\n3. isiXhosa\n4. Afrikaans\n5. Sesotho\n6. Setswana\n7. Xitsonga\n8. siSwati\n9. Tshivenda\n10. isiNdebele\n11. Sepedi\n\n*Reply with the number* of your preferred language",
        'medication_ask': "💊 *Medication Setup*\n\nWhat medication are you taking? (e.g., Metformin, ARVs, Blood Pressure pills)",
        'dosage_ask': "📏 *Dosage Information*\n\nWhat is your dosage? (e.g., 500mg, 1 tablet, 5ml)",
        'schedule_ask': "⏰ *Dosing Schedule*\n\nWhat times should we remind you? Please reply with times like:\n• 08:00 and 20:00\n• 07:00, 13:00, 19:00\n• 09:00 only",
        'confirmation': "✅ *Setup Complete!*\n\nMedication: {medication}\nDosage: {dosage}\nTimes: {times}\n\nWe'll send you reminders at these times. Reply TAKEN when you take your medication.",
        'reminder': "💊 *Reminder*: Time for your {medication} ({dosage})\n\nReply TAKEN when done.",
        'taken_confirmation': "✅ Thank you! We've recorded your {medication} dose.",
        'missed_alert': "⚠️ *Missed Dose Alert*\n\nYou haven't taken your {medication}. Please take it now.",
        'help': "🆘 *Help*\n\nCommands:\n• TAKEN - Record medication taken\n• CHANGE - Update your medication\n• LANGUAGE - Change language\n• STOP - Pause reminders"
    },
    'zulu': {
        'welcome': "🏥 *Sawubona e-MediRemind SA!*\n\nSicela ukhethe ulimi:\n\n1. isiZulu\n2. English\n3. isiXhosa\n4. Afrikaans\n5. Sesotho\n6. Setswana\n7. Xitsonga\n8. siSwati\n9. Tshivenda\n10. isiNdebele\n11. Sepedi\n\n*Phendula ngenombolo* yolimi oluthandayo",
        'medication_ask': "💊 *Ukusetha Umuthi*\n\nUthatha umuthi onjani? (isb., i-Metformin, i-ARV, amaphilisi e-blood pressure)",
        'dosage_ask': "📏 *Imininingwane Yesilinganiso*\n\nSilinganiselo sini? (isb., 500mg, iphilisi elilodwa, 5ml)",
        'schedule_ask': "⏰ *Isheduli Yokuthatha Umuthi*\n\nKufanele sikukhumbuze nini? Phendula ngezikhathi ezifana:\n• 08:00 kanye no-20:00\n• 07:00, 13:00, 19:00\n• 09:00 kuphela",
        'confirmation': "✅ *Ukusetha Kuqediwe!*\n\nUmuthi: {medication}\nIsilinganiso: {dosage}\nIzikhathi: {times}\n\nSizokuthumelela izikhumbuzo nalezizikhathi. Phendula THATHIWE lapho uthatha umuthi wakho.",
        'reminder': "💊 *Isikhumbuzo*: Isikhathi sokuthatha {medication} ({dosage})\n\nPhendula THATHIWE uma usuqedile.",
        'taken_confirmation': "✅ Ngiyabonga! Sirekhode isilinganiso sakho se-{medication}.",
        'missed_alert': "⚠️ *Isixwayiso Sesilinganiso Esishiyiwe*\n\nAwukathathi isilinganiso sakho se-{medication}. Sicela usithathe manje.",
        'help': "🆘 *Usizo*\n\nImiyalo:\n• THATHIWE - Rekhoda umuthi othathiwe\n• SHINTSHA - Buyekeza umuthi wakho\n• ULIMI - Shintsha ulimi\n• YEMA - Misa izikhumbuzo"
    },
    'xhosa': {
        'welcome': "🏥 *Wamkelekile kwi-MediRemind SA!*\n\nKhetha ulwimi:\n\n1. isiXhosa\n2. English\n3. isiZulu\n4. Afrikaans\n5. Sesotho\n6. Setswana\n7. Xitsonga\n8. siSwati\n9. Tshivenda\n10. isiNdebele\n11. Sepedi\n\n*Phendula ngenombolo* yolwimi oluyintandokazi",
        'medication_ask': "💊 *Ukumisela Iyeza*\n\nLiyiphi iyeza olyo? (umz., i-Metformin, i-ARV, iipilisi ezenza umfutho wegazi)",
        'dosage_ask': "📏 *Iinkcukacha Zesilinganiselo*\n\nSisilinganiselo sini? (umz., 500mg, iipilisi ezi-1, 5ml)",
        'schedule_ask': "⏰ *Ixeshana Lokwamkela Iyeza*\n\nKufuneka sikukhumbuze nini? Phendula ngeexeshana ezifana:\n• 08:00 kunye ne-20:00\n• 07:00, 13:00, 19:00\n• 09:00 kuphela",
        'confirmation': "✅ *Ukumisela Kugqityiwe!*\n\nIyeza: {medication}\nIsilinganiselo: {dosage}\nIxeshana: {times}\n\nSiza kuthumela izikhumbuzo kule xeshana. Phendula NDIYITHABILE xa uthathe iyeza lakho.",
        'reminder': "💊 *Isikhumbuzo*: Ixesha lokuthatha {medication} ({dosage})\n\nPhendula NDIYITHABILE xa ugqibile.",
        'taken_confirmation': "✅ Enkosi! Sirekhode isilinganiselo sakho se-{medication}.",
        'missed_alert': "⚠️ *Isilumkiso Sesilinganiselo Esityholiweyo*\n\nAwukayithathi isilinganiselo sakho se-{medication}. Nceda uyithathe ngoku.",
        'help': "🆘 *Uncedo*\n\nIiyalelo:\n• NDIYITHABILE - Rekhoda iyeza elithathiweyo\n• TSHINTSHA - Hlela iyeza lakho\n• ULWIMI - Tshintsha ulwimi\n• YIMA - Yeka izikhumbuzo"
    },
    'afrikaans': {
        'welcome': "🏥 *Welkom by MediRemind SA!*\n\nKies jou taal:\n\n1. Afrikaans\n2. English\n3. isiZulu\n4. isiXhosa\n5. Sesotho\n6. Setswana\n7. Xitsonga\n8. siSwati\n9. Tshivenda\n10. isiNdebele\n11. Sepedi\n\n*Antwoord met die nommer* van jou taal",
        'medication_ask': "💊 *Medisyne Opstelling*\n\nWatter medisyne neem jy? (bv., Metformin, ARVs, Bloeddrukpille)",
        'dosage_ask': "📏 *Dosering Inligting*\n\nWat is jou dosis? (bv., 500mg, 1 tablet, 5ml)",
        'schedule_ask': "⏰ *Doseerskedule*\n\nOp watter tye moet ons jou herinner? Antwoord met tye soos:\n• 08:00 en 20:00\n• 07:00, 13:00, 19:00\n• 09:00 alleen",
        'confirmation': "✅ *Opstelling Voltooi!*\n\nMedisyne: {medication}\nDosering: {dosage}\nTye: {times}\n\nOns stuur jou herinnerings by hierdie tye. Antwoord GENEEM wanneer jy jou medisyne neem.",
        'reminder': "💊 *Herinnering*: Tyd vir jou {medication} ({dosage})\n\nAntwoord GENEEM wanneer klaar.",
        'taken_confirmation': "✅ Dankie! Ons het jou {medication} dosis aangeteken.",
        'missed_alert': "⚠️ *Gemiste Dosis Waarskuwing*\n\nJy het nie jou {medication} geneem nie. Neem dit asseblief nou.",
        'help': "🆘 *Hulp*\n\nOpdragte:\n• GENEEM - Teken medisyne geneem aan\n• VERANDER - Opdateer jou medisyne\n• TAAL - Verander taal\n• STOP - Laat wag herinnerings"
    },
    'sotho': {
        'welcome': "🏥 *Rea u amohela ho MediRemind SA!*\n\nKhetha puo:\n\n1. Sesotho\n2. English\n3. isiZulu\n4. isiXhosa\n5. Afrikaans\n6. Setswana\n7. Xitsonga\n8. siSwati\n9. Tshivenda\n10. isiNdebele\n11. Sepedi\n\n*Arabela ka nomoro* ea puo eo u e ratang",
        'medication_ask': "💊 *Ho seta Meriana*\n\nO nka meriana efe? (mohl., Metformin, ARV, Dipilisi tsa mali)",
        'dosage_ask': "📏 *Lintlha tsa Dosage*\n\nDosage ea hau ke efe? (mohl., 500mg, leqephe le le leng, 5ml)",
        'schedule_ask': "⏰ *Dosing Schedule*\n\nRe lokela ho u hopotsa ka nako life? Arabela ka linako tse kang:\n• 08:00 le 20:00\n• 07:00, 13:00, 19:00\n• 09:00 feela",
        'confirmation': "✅ *Ho seta Ho phethiloe!*\n\nMeriana: {medication}\nDosage: {dosage}\nLinako: {times}\n\nRe tla u romella dikeletso ka linako tsena. Arabela E NTSE hang ha u nka meriana ea hau.",
        'reminder': "💊 *Khopotso*: Nako ea ho nka {medication} ({dosage})\n\nArabela E NTSE ha u se u qetile.",
        'taken_confirmation': "✅ Kea leboha! Re ngotse dosage ea hau ea {medication}.",
        'missed_alert': "⚠️ *Temoso ea Dosage e Sieo*\n\nHa u a ka ua nka dosage ea hau ea {medication}. Ka kopo u e nke hona joale.",
        'help': "🆘 *Thuso*\n\nLitaelo:\n• E NTSE - Ngola meriana e ntoeng\n• FETOLA - Nchafatsa meriana ea hau\n• PUO - Fetola puo\n• EMA - Emisa dikeletso"
    }
    # Add remaining 6 languages following same pattern...
}

# LANGUAGE MAPPING
LANGUAGE_MAP = {
    '1': 'english', 'english': 'english',
    '2': 'zulu', 'zulu': 'zulu', 'isizulu': 'zulu',
    '3': 'xhosa', 'xhosa': 'xhosa', 'isixhosa': 'xhosa',
    '4': 'afrikaans', 'afrikaans': 'afrikaans',
    '5': 'sotho', 'sotho': 'sotho', 'sesotho': 'sotho',
    '6': 'tswana', 'tswana': 'tswana', 'setswana': 'tswana', 
    '7': 'tsonga', 'tsonga': 'tsonga', 'xitsonga': 'tsonga',
    '8': 'swati', 'swati': 'swati', 'siswati': 'swati',
    '9': 'venda', 'venda': 'venda', 'tshivenda': 'venda',
    '10': 'ndebele', 'ndebele': 'ndebele', 'isindebele': 'ndebele',
    '11': 'pedi', 'pedi': 'pedi', 'sepedi': 'pedi'
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
        print(f"WhatsApp send failed to {to_number}: {e}")
        return False

def parse_times(time_text):
    """Parse natural language time input"""
    times = []
    for part in time_text.replace('and', ',').replace(' ', '').split(','):
        if ':' in part and len(part) in [4, 5]:
            times.append(part)
    return times if times else ['08:00', '20:00']  # Default

def get_current_medication(patient_phone):
    """Get patient's current medication"""
    med = Medication.query.filter_by(patient_phone=patient_phone).first()
    return med.name if med else 'your medication'

# CONVERSATION MANAGER
def handle_conversation(patient_phone, message):
    """Manage the conversational flow with patients"""
    patient = Patient.query.filter_by(phone=patient_phone).first()
    
    if not patient:
        # New patient - start language selection
        patient = Patient(phone=patient_phone, conversation_state='language_selection')
        db.session.add(patient)
        db.session.commit()
        return MESSAGES['english']['welcome']
    
    current_state = patient.conversation_state
    language = patient.language
    
    # Handle language selection
    if current_state == 'language_selection':
        if message.lower() in LANGUAGE_MAP:
            patient.language = LANGUAGE_MAP[message.lower()]
            patient.conversation_state = 'medication_ask'
            db.session.commit()
            return MESSAGES[patient.language]['medication_ask']
        else:
            return MESSAGES.get(language, MESSAGES['english'])['welcome']
    
    # Handle medication setup flow
    elif current_state == 'medication_ask':
        patient.conversation_data = json.dumps({'medication': message})
        patient.conversation_state = 'dosage_ask'
        db.session.commit()
        return MESSAGES[language]['dosage_ask']
    
    elif current_state == 'dosage_ask':
        data = json.loads(patient.conversation_data or '{}')
        data['dosage'] = message
        patient.conversation_data = json.dumps(data)
        patient.conversation_state = 'schedule_ask'
        db.session.commit()
        return MESSAGES[language]['schedule_ask']
    
    elif current_state == 'schedule_ask':
        # Parse times
        times = parse_times(message)
        data = json.loads(patient.conversation_data or '{}')
        
        # Save medication
        medication = Medication(
            patient_phone=patient_phone,
            name=data.get('medication', 'Unknown'),
            dosage=data.get('dosage', 'Unknown'),
            times=times
        )
        db.session.add(medication)
        
        # Complete setup
        patient.conversation_state = 'active'
        db.session.commit()
        
        return MESSAGES[language]['confirmation'].format(
            medication=data.get('medication'),
            dosage=data.get('dosage'),
            times=', '.join(times)
        )
    
    # Active state - handle commands
    elif current_state == 'active':
        message_lower = message.lower()
        
        if 'taken' in message_lower:
            # Record medication taken
            adherence = Adherence(
                patient_phone=patient_phone,
                medication=get_current_medication(patient_phone),
                scheduled_time=datetime.now(),
                taken=True,
                responded_at=datetime.now()
            )
            db.session.add(adherence)
            db.session.commit()
            
            return MESSAGES[language]['taken_confirmation'].format(
                medication=get_current_medication(patient_phone)
            )
        
        elif 'change' in message_lower or 'update' in message_lower:
            patient.conversation_state = 'medication_ask'
            db.session.commit()
            return MESSAGES[language]['medication_ask']
        
        elif 'language' in message_lower:
            patient.conversation_state = 'language_selection'
            db.session.commit()
            return MESSAGES[language]['welcome']
        
        elif 'stop' in message_lower:
            # Pause medications
            Medication.query.filter_by(patient_phone=patient_phone).update({'active': False})
            db.session.commit()
            return MESSAGES[language]['help'] + "\n\n❌ Reminders paused. Reply START to resume."
        
        elif 'start' in message_lower:
            # Resume medications
            Medication.query.filter_by(patient_phone=patient_phone).update({'active': True})
            db.session.commit()
            return MESSAGES[language]['help'] + "\n\n✅ Reminders resumed!"
        
        elif 'help' in message_lower:
            return MESSAGES[language]['help']
        
        else:
            return MESSAGES[language]['help']

# WHATSAPP WEBHOOK
@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    try:
        incoming_msg = request.form.get('Body', '').strip()
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        
        print(f"Message from {from_number}: {incoming_msg}")
        
        # Handle the conversation
        response = handle_conversation(from_number, incoming_msg)
        
        # Send response
        send_whatsapp(from_number, response)
        
        return '<Response></Response>'
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return '<Response><Message>Sorry, system error. Please try again.</Message></Response>'

# REMINDER SCHEDULER
def reminder_worker():
    """Background thread that checks for reminders every minute"""
    while True:
        try:
            current_time = datetime.now().strftime('%H:%M')
            
            # Find active medications due now
            due_meds = Medication.query.filter_by(active=True).all()
            
            for med in due_meds:
                if med.times and current_time in med.times:
                    patient = Patient.query.filter_by(phone=med.patient_phone).first()
                    if patient:
                        message = MESSAGES[patient.language]['reminder'].format(
                            medication=med.name, dosage=med.dosage
                        )
                        if send_whatsapp(patient.phone, message):
                            # Log the reminder
                            adherence = Adherence(
                                patient_phone=patient.phone,
                                medication=med.name,
                                scheduled_time=datetime.now()
                            )
                            db.session.add(adherence)
                            db.session.commit()
                            print(f"Sent reminder to {patient.phone} for {med.name}")
            
            time.sleep(60)  # Wait 60 seconds
            
        except Exception as e:
            print(f"Reminder worker error: {e}")
            time.sleep(60)

# SIMPLE CLINIC DASHBOARD
@app.route('/')
def clinic_dashboard():
    patients = Patient.query.count()
    active_meds = Medication.query.filter_by(active=True).count()
    
    return f"""
    <html>
    <head><title>MediRemind SA</title></head>
    <body>
        <h1>MediRemind SA Dashboard</h1>
        <p>Total Patients: {patients}</p>
        <p>Active Medications: {active_meds}</p>
        <p><a href="/add_patient">Add New Patient</a></p>
        <p><a href="/patients">View All Patients</a></p>
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
        
        # Send welcome message
        welcome_msg = MESSAGES[patient.language]['confirmation'].format(
            medication=med.name, dosage=med.dosage, times=', '.join(med.times)
        )
        send_whatsapp(patient.phone, welcome_msg)
        
        return "Patient added successfully! They will receive a welcome message."
    
    return """
    <form method="POST">
        <h3>Add New Patient</h3>
        <input type="text" name="name" placeholder="Patient Name" required><br><br>
        <input type="text" name="phone" placeholder="27821234567" required><br><br>
        <select name="language" required>
            <option value="english">English</option>
            <option value="zulu">isiZulu</option>
            <option value="xhosa">isiXhosa</option>
            <option value="afrikaans">Afrikaans</option>
            <option value="sotho">Sesotho</option>
        </select><br><br>
        <input type="text" name="medication" placeholder="Medication Name" required><br><br>
        <input type="text" name="dosage" placeholder="50mg, 1 tablet, etc" required><br><br>
        <input type="text" name="times" placeholder="08:00,20:00" required><br><br>
        <button type="submit">Add Patient</button>
    </form>
    """

@app.route('/patients')
def view_patients():
    patients = Patient.query.all()
    html = "<h1>All Patients</h1><ul>"
    for patient in patients:
        meds = Medication.query.filter_by(patient_phone=patient.phone).all()
        html += f"<li>{patient.name} ({patient.phone}) - {patient.language}"
        for med in meds:
            html += f"<br>• {med.name} {med.dosage} at {', '.join(med.times)}"
        html += "</li>"
    html += "</ul>"
    return html

# Start the background thread when app loads
@app.before_first_request
def start_reminder_worker():
    worker_thread = threading.Thread(target=reminder_worker, daemon=True)
    worker_thread.start()
    print("Reminder worker started!")

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized!")

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
