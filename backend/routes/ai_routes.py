from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import anthropic
import os

ai_bp = Blueprint('ai', __name__)

SYSTEM_PROMPT = """You are SAIL Advisor, an expert AI assistant built into SAIL 
(Student-Athlete AI Locator). You help student-athletes, parents, and coaches 
navigate the American college athletic recruiting process.

You are an expert in:
- NCAA Division I, II, and III rules and scholarship limits
- NAIA and NJCAA (Junior College) opportunities  
- NCAA Eligibility Center registration process
- Academic eligibility requirements (GPA, SAT/ACT, core courses)
- The recruiting calendar and coach contact rules
- Athletic scholarship types: full ride, partial, equivalency, headcount
- Writing effective recruiting emails to coaches
- F-1 student visa requirements for international athletes
- FAFSA and financial aid process
- Campus visit types: official vs unofficial
- The National Letter of Intent (NLI)
- Transfer portal rules
- Life as a college athlete in America

Tone: Warm, encouraging, and professional. Like a trusted advisor.
Audience: High school athletes (14-18), their parents, and coaches.
Format: Use bullet points for lists. Keep answers clear and actionable.
Always recommend verifying specific details directly with athletic departments."""

@ai_bp.post('/api/ai/chat')
@login_required
def chat():
    data = request.get_json() or {}
    messages = data.get('messages', [])
    
    if not messages:
        return jsonify({'error': 'No messages provided.'}), 400

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'AI service not configured yet.'}), 503

    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        # Only send role and content to Claude
        clean_messages = [
            {'role': m['role'], 'content': m['content']}
            for m in messages
            if m.get('role') in ('user', 'assistant')
        ]

        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=clean_messages
        )

        reply = response.content[0].text
        return jsonify({'reply': reply})

    except Exception as e:
        return jsonify({'error': f'AI error: {str(e)}'}), 503


@ai_bp.post('/api/ai/generate-email')
@login_required  
def generate_email():
    data = request.get_json() or {}
    school = data.get('university_name', '')
    coach  = data.get('coach_name', '')

    if not school:
        return jsonify({'error': 'School name is required.'}), 400

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'AI service not configured.'}), 503

    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        coach_line = f"Coach {coach}" if coach else "the coaching staff"
        
        prompt = f"""Write a professional athletic recruiting email to {coach_line} 
at {school}. The email should:
- Be 200-250 words
- Open with genuine interest in the program
- Mention the athlete is seeking scholarship opportunities
- Be enthusiastic but professional
- End with a clear call to action
- Sound like a real high school student wrote it

Return only the email text starting with Dear..."""

        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=600,
            messages=[{'role': 'user', 'content': prompt}]
        )

        return jsonify({'email': response.content[0].text})

    except Exception as e:
        return jsonify({'error': f'AI error: {str(e)}'}), 503