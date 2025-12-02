from flask import Flask, request, render_template, jsonify, redirect, url_for, session
import base64
import os
import csv
import sys
from datetime import datetime
import json

app = Flask(__name__)
LIC_STR = '' 
app.secret_key = 'your_secret_key_change_in_production'

# Data storage for biometric workflows
registration_data = {}
login_scan_data = {}
voting_data = {}

# CSV file paths
VOTERS_CSV = 'voters.csv'
VOTES_CSV = 'votes.csv'
CANDIDATES_CSV = 'candidates.csv'
DAILY_VOTES_CSV = 'daily_votes.csv'

# Initialize CSV files if they don't exist
def init_csv_files():
    # Voters CSV: voter_id, name, template_base64, bmp_base64, registration_date
    if not os.path.exists(VOTERS_CSV):
        with open(VOTERS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['voter_id', 'name', 'template_base64', 'bmp_base64', 'registration_date'])
    
    # Votes CSV: date, voter_id, name, state, constituency, candidate_name, party, timestamp
    if not os.path.exists(VOTES_CSV):
        with open(VOTES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'voter_id', 'name', 'state', 'constituency', 'candidate_name', 'party', 'timestamp'])
    
    # Daily votes CSV: date, voter_id, voted, timestamp (to track voting within 75 hours)
    if not os.path.exists(DAILY_VOTES_CSV):
        with open(DAILY_VOTES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'voter_id', 'voted', 'timestamp'])

def TranslateErrorNumber(ErrorNumber):
    match ErrorNumber:
        case 3:
            return "Failure to reach SecuGen Fingerprint Scanner"
        case 51:
            return "System file load failure"
        case 52:
            return "Sensor chip initialization failed"
        case 53:
            return "Device not found"
        case 54:
            return "Fingerprint image capture timeout"
        case 55:
            return "No device available"
        case 56:
            return "Driver load failed"
        case 57:
            return "Wrong Image"
        case 58:
            return "Lack of bandwidth"
        case 59:
            return "Device Busy"
        case 60:
            return "Cannot get serial number of the device"
        case 61:
            return "Unsupported device"
        case 63:
            return "SgiBioSrv didn't start; Try image capture again"
        case _:
            return "Unknown error code or Update code to reflect latest result"

# Helper function to safely convert form values to integers
def get_int_form_value(form, key, default=0):
    """Safely get integer value from form, handling empty strings and None"""
    value = form.get(key, default)
    if value == '' or value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# Save voter to CSV
def save_voter(voter_id, name, template_base64, bmp_base64):
    with open(VOTERS_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([voter_id, name, template_base64, bmp_base64, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

# Get all voters from CSV
def get_all_voters():
    voters = []
    if os.path.exists(VOTERS_CSV):
        try:
            # Increase field size limit for CSV with large base64 strings
            original_limit = csv.field_size_limit()
            try:
                csv.field_size_limit(min(2**31-1, sys.maxsize))
            except:
                pass
            
            with open(VOTERS_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                row_count = 0
                for row in reader:
                    row_count += 1
                    try:
                        voter_id = (row.get('voter_id') or '').strip()
                        template = (row.get('template_base64') or '').strip()
                        name = (row.get('name') or '').strip()
                        bmp = (row.get('bmp_base64') or '').strip()
                        reg_date = (row.get('registration_date') or '').strip()
                        
                        # Check if row has required fields and template_base64 is not empty
                        if voter_id and template and len(template) > 10:
                            voters.append({
                                'voter_id': voter_id,
                                'name': name,
                                'template_base64': template,
                                'bmp_base64': bmp,
                                'registration_date': reg_date
                            })
                            print(f"✓ Loaded voter {row_count}: ID={voter_id}, Name={name}, Template length={len(template)}")
                        else:
                            print(f"✗ Skipped row {row_count}: voter_id={bool(voter_id)}, template_len={len(template) if template else 0}")
                    except Exception as row_error:
                        print(f"✗ Error processing row {row_count}: {row_error}")
                        continue
                
                print(f"CSV reading complete: {row_count} rows processed, {len(voters)} valid voters loaded")
            
            # Restore original limit
            try:
                csv.field_size_limit(original_limit)
            except:
                pass
                
        except Exception as e:
            print(f"ERROR reading voters CSV: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"WARNING: VOTERS_CSV file does not exist: {VOTERS_CSV}")
    
    print(f"get_all_voters returning {len(voters)} voters")
    return voters

# Check if voter ID exists
def voter_id_exists(voter_id):
    voters = get_all_voters()
    return any(v['voter_id'].upper() == voter_id.upper() for v in voters)

# Check if voter has already voted within the last 75 hours
def has_voted_today(voter_id):
    current_time = datetime.now()
    if os.path.exists(DAILY_VOTES_CSV):
        try:
            with open(DAILY_VOTES_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('voter_id', '').upper() == voter_id.upper():
                        # Check if timestamp exists (new format) or use date (old format for backward compatibility)
                        timestamp_str = row.get('timestamp', '')
                        if timestamp_str:
                            try:
                                vote_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                time_diff = current_time - vote_time
                                # Check if voted within last 75 hours (75 * 3600 = 270,000 seconds)
                                if time_diff.total_seconds() < (75 * 3600):  # 75 hours in seconds
                                    return True
                            except ValueError:
                                # If timestamp parsing fails, fall back to date check
                                pass
                        else:
                            # Backward compatibility: check by date if no timestamp
                            vote_date = row.get('date', '')
                            if vote_date:
                                try:
                                    vote_datetime = datetime.strptime(vote_date, '%Y-%m-%d')
                                    time_diff = current_time - vote_datetime
                                    # If old format, assume vote was at start of day, check if within 75 hours
                                    if time_diff.total_seconds() < (75 * 3600):
                                        return True
                                except ValueError:
                                    pass
        except Exception as e:
            print(f"Error checking daily votes: {e}")
    return False

# Mark voter as voted (with timestamp for 75-hour tracking)
def mark_voted_today(voter_id):
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(DAILY_VOTES_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([today, voter_id, 'yes', timestamp])

# Save vote to CSV
def save_vote(voter_id, name, state, constituency, candidate_name, party):
    today = datetime.now().strftime('%Y-%m-%d')
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(VOTES_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([today, voter_id, name, state, constituency, candidate_name, party, timestamp])

# Get votes for results
def get_votes():
    votes = {}
    if os.path.exists(VOTES_CSV):
        try:
            with open(VOTES_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('constituency') and row.get('candidate_name'):
                        constituency = row['constituency']
                        candidate = f"{row['candidate_name']} ({row['party']})"
                        if constituency not in votes:
                            votes[constituency] = {}
                        if candidate not in votes[constituency]:
                            votes[constituency][candidate] = 0
                        votes[constituency][candidate] += 1
        except Exception as e:
            print(f"Error reading votes CSV: {e}")
    return votes

# Get vote log
def get_vote_log():
    log = []
    if os.path.exists(VOTES_CSV):
        try:
            with open(VOTES_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('voter_id'):  # Skip empty rows
                        log.append(row)
        except Exception as e:
            print(f"Error reading vote log: {e}")
    return log

# Get voter by ID
def get_voter_by_id(voter_id):
    voters = get_all_voters()
    for v in voters:
        if v['voter_id'].upper() == voter_id.upper():
            return v
    return None

# Check if biometric template already exists (prevent duplicate registration)
def biometric_exists(template_base64):
    voters = get_all_voters()
    for voter in voters:
        if voter['template_base64'] == template_base64:
            return True
    return False

# ========== DELETE FUNCTIONS ==========

# Delete all daily votes data (keep header)
def delete_daily_votes():
    try:
        with open(DAILY_VOTES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'voter_id', 'voted', 'timestamp'])
        return True, "Daily votes data deleted successfully"
    except Exception as e:
        return False, f"Error deleting daily votes: {str(e)}"

# Delete all voters data (keep header)
def delete_voters():
    try:
        with open(VOTERS_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['voter_id', 'name', 'template_base64', 'bmp_base64', 'registration_date'])
        return True, "Voters data deleted successfully"
    except Exception as e:
        return False, f"Error deleting voters: {str(e)}"

# Delete all votes data (keep header)
def delete_votes():
    try:
        with open(VOTES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'voter_id', 'name', 'state', 'constituency', 'candidate_name', 'party', 'timestamp'])
        return True, "Votes data deleted successfully"
    except Exception as e:
        return False, f"Error deleting votes: {str(e)}"

# Delete all candidates data (keep header)
def delete_candidates():
    try:
        with open(CANDIDATES_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['_id', 'State', 'Constituency', 'Party', 'Candidate Name'])
        return True, "Candidates data deleted successfully"
    except Exception as e:
        return False, f"Error deleting candidates: {str(e)}"

# ========== ROUTES ==========

@app.route('/')
def home():
    return render_template('home.html')

# ========== REGISTRATION FLOW ==========

@app.route('/register', methods=['GET', 'POST'])
def register():
    input_data = {
        'SecuGen_Lic': LIC_STR,
        'Timeout': 10000,
        'Quality': 50,
        'TemplateFormat': 'ISO',
        'ImageWSQRate': '0.75'
    }
    return render_template('register.html', user_input=input_data)

@app.route('/register_scan', methods=['POST'])
def register_scan():
    ErrorNumber = get_int_form_value(request.form, 'ErrorCode', 0)
    if ErrorNumber > 0:
        return render_template('error.html', error=ErrorNumber, errordescription=TranslateErrorNumber(ErrorNumber))
    
    registration_data['template'] = request.form.get('TemplateBase64')
    registration_data['BMPBase64'] = request.form.get('BMPBase64')
    registration_data['Manufacturer'] = request.form.get('Manufacturer')
    registration_data['Model'] = request.form.get('Model')
    registration_data['SerialNumber'] = request.form.get('SerialNumber')
    
    return render_template('register_form.html', metadata=registration_data)

@app.route('/save_registration', methods=['POST'])
def save_registration():
    voter_id = request.form.get('voter_id', '').strip().upper()
    name = request.form.get('name', '').strip()
    template_base64 = registration_data.get('template', '')
    bmp_base64 = registration_data.get('BMPBase64', '')
    
    if not voter_id or not name or not template_base64:
        return render_template('error.html', error=400, errordescription="Missing required information")
    
    # Check if voter ID already exists
    if voter_id_exists(voter_id):
        return render_template('error.html', error=409, errordescription=f"Voter ID {voter_id} is already registered")
    
    # Check if biometric already exists
    if biometric_exists(template_base64):
        return render_template('error.html', error=409, errordescription="This biometric is already registered with another voter ID")
    
    # Save voter
    save_voter(voter_id, name, template_base64, bmp_base64)
    
    return render_template('registration_success.html', voter_id=voter_id, name=name)

# ========== LOGIN FLOW ==========

@app.route('/login', methods=['GET', 'POST'])
def login():
    input_data = {
        'SecuGen_Lic': LIC_STR,
        'Timeout': 10000,
        'Quality': 50,
        'TemplateFormat': 'ISO',
        'ImageWSQRate': '0.75'
    }
    return render_template('login.html', user_input=input_data)

@app.route('/login_scan1', methods=['POST'])
def login_scan1():
    ErrorNumber = get_int_form_value(request.form, 'ErrorCode', 0)
    if ErrorNumber > 0:
        return render_template('error.html', error=ErrorNumber, errordescription=TranslateErrorNumber(ErrorNumber))
    
    login_scan_data['template1'] = request.form.get('TemplateBase64', '').strip()
    login_scan_data['BMPBase64_1'] = request.form.get('BMPBase64', '').strip()
    
    print(f"Login scan1: Template1 length={len(login_scan_data.get('template1', ''))}, BMP1 length={len(login_scan_data.get('BMPBase64_1', ''))}")
    
    if not login_scan_data['template1']:
        return render_template('error.html', error=400, errordescription="Fingerprint template not captured. Please try again.")
    
    input_data = {
        'SecuGen_Lic': LIC_STR,
        'Timeout': 10000,
        'Quality': 50,
        'TemplateFormat': 'ISO',
        'ImageWSQRate': '0.75'
    }
    return render_template('login_scan2.html', user_input=input_data, metadata1={'BMPBase64': login_scan_data['BMPBase64_1']})

@app.route('/login_scan2', methods=['POST'])
def login_scan2():
    ErrorNumber = get_int_form_value(request.form, 'ErrorCode', 0)
    if ErrorNumber > 0:
        return render_template('error.html', error=ErrorNumber, errordescription=TranslateErrorNumber(ErrorNumber))
    
    login_scan_data['template2'] = request.form.get('TemplateBase64', '').strip()
    login_scan_data['BMPBase64_2'] = request.form.get('BMPBase64', '').strip()
    
    print(f"Login scan2: Template2 length={len(login_scan_data.get('template2', ''))}, BMP2 length={len(login_scan_data.get('BMPBase64_2', ''))}")
    print(f"Template1 from scan1 length={len(login_scan_data.get('template1', ''))}")
    
    # Validate templates exist
    if not login_scan_data.get('template1') or not login_scan_data.get('template2'):
        return render_template('error.html', error=400, errordescription="Fingerprint templates missing. Please start login process again.")
    
    # Ensure templates are passed correctly
    template1 = login_scan_data.get('template1', '')
    template2 = login_scan_data.get('template2', '')
    
    return render_template('login_compare.html', 
                          template1=template1,
                          template2=template2,
                          metadata1={'BMPBase64': login_scan_data.get('BMPBase64_1', '')},
                          metadata2={'BMPBase64': login_scan_data.get('BMPBase64_2', '')},
                          user_input={'TemplateFormat': 'ISO', 'SecuGen_Lic': LIC_STR})

@app.route('/login_verify', methods=['POST'])
def login_verify():
    matched_voter_id = request.form.get('matched_voter_id', '').strip()
    matching_score = get_int_form_value(request.form, 'MatchingScore', 0)
    error_code = get_int_form_value(request.form, 'ErrorCode', 0)
    
    print(f"Login verify: voter_id={matched_voter_id}, score={matching_score}, error={error_code}")
    
    if error_code > 0:
        return render_template('error.html', error=error_code, errordescription=TranslateErrorNumber(error_code))
    
    # Lower threshold to 20 as requested by user
    if not matched_voter_id or matching_score < 20:
        return render_template('error.html', error=401, errordescription=f"Biometric verification failed. Matching score: {matching_score} (minimum required: 20). Please try again.")
    
    # Check if already voted within last 75 hours
    if has_voted_today(matched_voter_id):
        return render_template('error.html', error=403, errordescription="You have already voted recently. You can only vote once every 75 hours.")
    
    # Store in session for voting flow
    session['voter_id'] = matched_voter_id
    voter = get_voter_by_id(matched_voter_id)
    if voter:
        session['voter_name'] = voter['name']
    
    # Redirect to voting system
    return redirect(url_for('voting_system'))

# ========== VOTING SYSTEM ==========

@app.route('/voting', methods=['GET', 'POST'])
def voting_system():
    if 'voter_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('voting_system.html', voter_id=session.get('voter_id'), voter_name=session.get('voter_name', ''))

@app.route('/get_candidates_json', methods=['GET'])
def get_candidates_json():
    candidates = []
    if os.path.exists(CANDIDATES_CSV):
        try:
            with open(CANDIDATES_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('State') or row.get('Candidate Name'):  # Skip empty rows
                        candidates.append(row)
        except Exception as e:
            print(f"Error reading candidates CSV: {e}")
    return jsonify(candidates)

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    if 'voter_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    voter_id = session['voter_id']
    voter_name = session.get('voter_name', '')
    
    # Check if already voted within last 75 hours
    if has_voted_today(voter_id):
        return jsonify({'error': 'Already voted within the last 75 hours'}), 403
    
    data = request.json
    state = data.get('state', '')
    constituency = data.get('constituency', '')
    candidate_name = data.get('candidate_name', '')
    party = data.get('party', '')
    
    # Save vote
    save_vote(voter_id, voter_name, state, constituency, candidate_name, party)
    
    # Mark as voted (within 75-hour window)
    mark_voted_today(voter_id)
    
    # Clear session
    session.clear()
    
    return jsonify({'success': True, 'message': 'Vote recorded successfully'})

# ========== ADMIN PANEL ==========

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == 'mini2025':
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('admin_login.html', error='Invalid password')
    return render_template('admin_login.html')

@app.route('/admin_panel', methods=['GET'])
def admin_panel():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    voters = get_all_voters()
    votes = get_votes()
    vote_log = get_vote_log()
    
    return render_template('admin_panel.html', voters=voters, votes=votes, vote_log=vote_log)

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('home'))

@app.route('/admin/upload_candidates', methods=['POST'])
def upload_candidates():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.endswith('.csv'):
        # Save uploaded CSV
        file.save(CANDIDATES_CSV)
        return jsonify({'success': True, 'message': 'Candidates uploaded successfully'})
    
    return jsonify({'error': 'Invalid file format'}), 400

@app.route('/admin/delete_daily_votes', methods=['POST'])
def admin_delete_daily_votes():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    success, message = delete_daily_votes()
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/admin/delete_voters', methods=['POST'])
def admin_delete_voters():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    success, message = delete_voters()
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/admin/delete_votes', methods=['POST'])
def admin_delete_votes():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    success, message = delete_votes()
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/admin/delete_candidates', methods=['POST'])
def admin_delete_candidates():
    if not session.get('admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    success, message = delete_candidates()
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 500

@app.route('/get_voters_json', methods=['GET'])
def get_voters_json():
    """API endpoint for frontend to get all voters for biometric comparison"""
    try:
        voters = get_all_voters()
        print(f"get_voters_json: Total voters from CSV: {len(voters)}")
        
        if not voters or len(voters) == 0:
            print("WARNING: No voters found in CSV file!")
            return jsonify([])
        
        # Filter and validate voters with templates
        valid_voters = []
        for voter in voters:
            template = voter.get('template_base64', '')
            voter_id = voter.get('voter_id', '')
            
            if voter_id and template and len(template.strip()) > 10:
                valid_voters.append({
                    'voter_id': voter_id,
                    'name': voter.get('name', ''),
                    'template_base64': template.strip(),
                    'bmp_base64': voter.get('bmp_base64', ''),
                    'registration_date': voter.get('registration_date', '')
                })
        
        print(f"get_voters_json: Valid voters with templates: {len(valid_voters)}")
        
        # Log first few voters for debugging
        for i, voter in enumerate(valid_voters[:3]):
            template_len = len(voter.get('template_base64', ''))
            print(f"Voter {i+1}: ID={voter.get('voter_id')}, Name={voter.get('name')}, Template length={template_len}")
        
        if len(valid_voters) == 0:
            print("WARNING: No valid voters with templates found!")
        
        return jsonify(valid_voters)
    except Exception as e:
        print(f"ERROR in get_voters_json: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'voters': []}), 500

# Initialize CSV files on startup
init_csv_files()

if __name__ == '__main__':
    app.run(debug=True)
