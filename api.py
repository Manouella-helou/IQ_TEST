from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
import datetime
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

IMAGE_DIRECTORY = '/Users/manouellahelou/Desktop/Project/images'

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Mysql@1234',
    'database': 'iq_test_db'
}

# Get database connection
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Create a session for a new user
@app.route('/create_session', methods=['POST'])
def create_session():
    data = request.json
    email = data.get('email')
    name = data.get('name')
    ip_address = data.get('ip_address')
    browser_info = data.get('browser_info')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if user exists
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if not user:
            # Create new user
            cursor.execute("""
                INSERT INTO users (username, email, password, created_at)
                VALUES (%s, %s, %s, %s)
            """, (name, email, "temporary_password", datetime.datetime.now()))
            user_id = cursor.lastrowid
        else:
            user_id = user[0]
        
        # Get first test ID
        cursor.execute("SELECT test_id FROM tests LIMIT 1")
        test_result = cursor.fetchone()
        
        if not test_result:
            # Create a default test if none exists
            cursor.execute("""
                INSERT INTO tests (title, description, time_limit, created_at)
                VALUES (%s, %s, %s, %s)
            """, ("Standard IQ Test", "A comprehensive IQ assessment", 60, datetime.datetime.now()))
            test_id = cursor.lastrowid
        else:
            test_id = test_result[0]
        
        # Create test session
        cursor.execute("""
            INSERT INTO test_sessions (test_id, user_id, start_time, status, ip_address, browser_info)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            test_id, 
            user_id, 
            datetime.datetime.now(),
            "in_progress",
            ip_address,
            browser_info
        ))
        
        session_id = cursor.lastrowid
        conn.commit()
        
        return jsonify({"session_id": session_id})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()

# Get questions for the test
@app.route('/get_questions', methods=['GET'])
def get_questions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Modified to select exactly 1 question from each section
        section1_count = 1
        section2_count = 1
        section3_count = 1
            
        all_questions = []
        
        # Get questions for each section separately
        for section_id in range(1, 4):
            count = 1  # Always select exactly 1 question per section
            
            # Get random questions for this section
            cursor.execute("""
                SELECT q.* FROM questions q
                WHERE q.section_id = %s
                ORDER BY RAND()
                LIMIT %s
            """, (section_id, count))
            
            section_questions = cursor.fetchall()
            print(f"Selected {len(section_questions)} questions for section {section_id}")
            
            for question in section_questions:
                # Get category name
                cursor.execute("SELECT name FROM categories WHERE category_id = %s", (question['category_id'],))
                category = cursor.fetchone()
                question['category_name'] = category['name'] if category else "Unknown Category"
                question['section_name'] = f"Section {section_id}"
                
                # Get options
                cursor.execute("SELECT * FROM answer_options WHERE question_id = %s", (question['question_id'],))
                options = cursor.fetchall()
                question['options'] = options
                
                all_questions.append(question)
        
        print(f"Total selected questions: {len(all_questions)}")
        return jsonify({"questions": all_questions})
    
    except Exception as e:
        print(f"Error getting questions: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()

# Save user answer
@app.route('/save_answer', methods=['POST'])
def save_answer():
    data = request.json
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    option_id = data.get('option_id')
    time_spent = data.get('time_spent', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if an answer already exists for this question in this session
        cursor.execute("""
            SELECT answer_id FROM user_answers 
            WHERE session_id = %s AND question_id = %s
        """, (session_id, question_id))
        
        existing_answer = cursor.fetchone()
        
        if existing_answer:
            # Update the existing answer
            cursor.execute("""
                UPDATE user_answers
                SET selected_option_id = %s, answer_time = %s, time_spent = %s
                WHERE session_id = %s AND question_id = %s
            """, (option_id, datetime.datetime.now(), time_spent, session_id, question_id))
        else:
            # Insert a new answer
            cursor.execute("""
                INSERT INTO user_answers (session_id, question_id, selected_option_id, answer_time, time_spent)
                VALUES (%s, %s, %s, %s, %s)
            """, (session_id, question_id, option_id, datetime.datetime.now(), time_spent))
        
        conn.commit()
        return jsonify({"success": True})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()

# Save proctoring event
@app.route('/proctor_event', methods=['POST'])
def proctor_event():
    data = request.json
    session_id = data.get('session_id')
    event_type = data.get('event_type')
    event_data = data.get('event_data')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO proctoring_events (session_id, event_type, event_time, event_data)
            VALUES (%s, %s, %s, %s)
        """, (session_id, event_type, datetime.datetime.now(), event_data))
        
        conn.commit()
        return jsonify({"success": True})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()

# Complete a test session
@app.route('/complete_session', methods=['POST'])
def complete_session():
    data = request.json
    session_id = data.get('session_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE test_sessions 
            SET status = 'completed', end_time = %s
            WHERE session_id = %s
        """, (datetime.datetime.now(), session_id))
        
        conn.commit()
        return jsonify({"success": True})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()

# Serve images - additional debugging
@app.route('/images/<path:filename>')
def serve_image(filename):
    # Extract just the filename without any path
    clean_filename = os.path.basename(filename)
    
    # Log the request for debugging
    print(f"Serving image: {clean_filename}")
    print(f"Image directory: {IMAGE_DIRECTORY}")
    
    # Check if file exists
    full_path = os.path.join(IMAGE_DIRECTORY, clean_filename)
    if not os.path.exists(full_path):
        print(f"WARNING: Image file does not exist: {full_path}")
        return jsonify({"error": "Image not found"}), 404
    
    return send_from_directory(IMAGE_DIRECTORY, clean_filename)

# Debug route to list all available images
@app.route('/debug/images')
def list_images():
    try:
        images = os.listdir(IMAGE_DIRECTORY)
        return jsonify({"images": images, "directory": IMAGE_DIRECTORY})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/ping')
def ping():
    """Simple endpoint to check if the API is running"""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
