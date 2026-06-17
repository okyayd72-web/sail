from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.app import limiter  
import anthropic
import os

ai_bp = Blueprint('ai', __name__)

SYSTEM_PROMPT = """You are SAIL Advisor, an expert AI assistant built into SAIL 
(Student-Athlete AI Locator). You help student-athletes, parents, and coaches 
navigate the American college tennis recruiting process.

You are an expert in:
- NCAA Division I, II, and III rules and tennis scholarship limits
- NAIA and NJCAA (Junior College) tennis opportunities  
- NCAA Eligibility Center registration process
- UTR (Universal Tennis Rating) and what levels fit each division
- Academic eligibility requirements (GPA, SAT/ACT, core courses)
- The recruiting calendar and coach contact rules
- Athletic scholarship types: full ride, partial, equivalency, headcount
- Writing effective recruiting emails to tennis coaches
- F-1 student visa requirements for international athletes
- FAFSA and financial aid process
- Campus visit types: official vs unofficial
- The National Letter of Intent (NLI)
- Transfer portal rules
- Life as a college tennis player in America

Tone: Warm, encouraging, and professional. Like a trusted advisor.
Audience: High school tennis players (14-18), their parents, and coaches.
Format: Use bullet points for lists. Keep answers clear and actionable.
Always recommend verifying specific details directly with athletic departments."""


@ai_bp.post('/api/ai/chat')
@login_required
@limiter.limit("20 per minute")
def chat():
    data = request.get_json() or {}
    messages = data.get('messages', [])

    if not messages:
        return jsonify({'error': 'No messages provided.'}), 400

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'AI service not configured yet.'}), 503

    try:
        # ── Analytics ──
        try:
            from backend.routes.analytics import track
            track('advisor_used', {'message_count': len(messages)})
        except Exception:
            pass

        client = anthropic.Anthropic(api_key=api_key)
        clean_messages = [
            {'role': m['role'], 'content': m['content']}
            for m in messages
            if m.get('role') in ('user', 'assistant')
        ]

        response = client.messages.create(
            model='claude-haiku-4-5',
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
@limiter.limit("10 per minute")
def generate_email():
    data   = request.get_json() or {}
    school = data.get('university_name', '').strip()
    coach  = data.get('coach_name', '').strip()

    if not school:
        return jsonify({'error': 'School name is required.'}), 400

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'AI service not configured.'}), 503

    # ── Fetch athlete profile ──
    try:
        from backend.routes.athlete import AthleteProfile
        from backend.routes.auth import User

        profile = AthleteProfile.query.filter_by(user_id=current_user.id).first()
        user    = User.query.filter_by(id=current_user.id).first()

        # Build profile context
        full_name      = f"{user.first_name} {user.last_name}" if user else "the athlete"
        first_name     = user.first_name if user else "the athlete"
        utr            = profile.utr_rating if profile else None
        gpa            = profile.gpa if profile else None
        grad_year      = profile.graduation_year if profile else None
        nationality    = profile.nationality if profile else None
        division       = profile.division_preference if profile else None
        gender         = profile.gender if profile else 'male'
        sat            = profile.sat_score if profile else None
        act            = profile.act_score if profile else None
        highlights     = profile.highlights_url if profile else None
        intended_major = profile.intended_major if profile else None
        preferred_city = profile.preferred_city if profile else None
        school_size    = profile.school_size_preference if profile else None
        state_prov     = profile.state_province if profile else None
        athletic_lvl   = profile.athletic_level if profile else None

    except Exception:
        # If profile fetch fails, still generate a basic email
        full_name = "the athlete"
        first_name = "the athlete"
        utr = gpa = grad_year = nationality = division = None
        gender = 'male'
        sat = act = highlights = state_prov = athletic_lvl = None
        intended_major = preferred_city = school_size = None

    # ── Build coach salutation ──
    if coach:
        # Extract last name if full name given
        parts = coach.strip().split()
        last_name = parts[-1] if parts else coach
        coach_salutation = f"Coach {last_name}"
    else:
        coach_salutation = "Coach"

    # ── Build team reference ──
    team_gender = "men's" if gender == 'male' else "women's"

    # ── Build profile lines ──
    profile_lines = []
    if grad_year:
        profile_lines.append(f"Graduation Year: {grad_year}")
    if gpa:
        profile_lines.append(f"GPA: {gpa:.1f}")
    if sat:
        profile_lines.append(f"SAT: {sat}")
    if act:
        profile_lines.append(f"ACT: {act}")
    if utr:
        profile_lines.append(f"UTR: {utr:.1f}")
    if intended_major:
        profile_lines.append(f"Intended Major: {intended_major}")
    if highlights:
        profile_lines.append(f"Highlight Video: {highlights}")
    profile_section = "\n".join(f"• {l}" for l in profile_lines) if profile_lines else "• Profile details to be filled in"

    # ── Build location line ──
    location_parts = [p for p in [state_prov, nationality] if p]
    location = ", ".join(location_parts) if location_parts else "my home country"

    # ── Build academic interest note (driven by intended major) ──
    if intended_major and intended_major not in ('Undecided', 'Other'):
        career_note = f"strong academic programs — especially for my intended major in {intended_major}"
    else:
        career_note = "the balance of academic excellence and competitive tennis"

    # ── Optional school-size note (only if the athlete expressed a preference) ──
    size_map = {
        'Small':  "I am especially drawn to the close-knit environment of a smaller school.",
        'Medium': "I am drawn to the balance a mid-sized university offers.",
        'Large':  "I am excited by the opportunities a large university environment provides.",
    }
    size_note = size_map.get(school_size, "")

    # ── Prompt ──
    prompt = f"""Write a professional tennis recruiting email using EXACTLY this template structure.
Fill in all bracketed placeholders using the athlete's real data provided below.
Do not change the structure. Do not add extra sections. Return only the email text.

ATHLETE DATA:
- Full name: {full_name}
- Location: {location}
- Graduation year: {grad_year or '[Graduation Year]'}
- UTR rating: {utr or '[UTR Rating]'}
- GPA: {gpa or '[GPA]'}
- SAT: {sat or 'Not provided'}
- ACT: {act or 'Not provided'}
- Gender: {gender}
- Athletic level: {athletic_lvl or 'competitive'}
- Intended major: {intended_major or 'Undecided'}
- School size preference: {school_size or 'No preference'}
- Highlight video: {highlights or '[Highlight Video Link]'}
- Target school: {school}
- Coach name/salutation: {coach_salutation}
- Team: {team_gender} tennis

EMAIL TEMPLATE TO FILL IN:
Hello {coach_salutation},

My name is {full_name}, and I am a {grad_year or '[Graduation Year]'} student-athlete from {location}. I am very interested in the opportunity to play for the {school} {team_gender} tennis team while pursuing my academic goals.

I currently have a UTR of {utr or '[UTR Rating]'} and have achieved the following:
• [Write 3-4 realistic achievements based on the athlete's UTR level and athletic level. For UTR {utr}, these should be appropriate competition results, rankings, or tournament wins.]

I am particularly interested in {school} because of its {career_note} and the culture of excellence within the tennis program. {size_note} After researching the university and team, I believe it would be an excellent fit for both my academic and athletic goals.

Here is some additional information about me:
{profile_section}

I would greatly appreciate the opportunity to learn more about your program and discuss how I may contribute to the team. Thank you for your time and consideration. I look forward to hearing from you.

Best regards,
{full_name}
{grad_year or ''}
UTR: {utr or '[UTR Rating]'}

Return only the email text. No subject line. No extra commentary."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=800,
            messages=[{'role': 'user', 'content': prompt}]
        )

        email_text = response.content[0].text

        # ── Analytics ──
        try:
            from backend.routes.analytics import track
            track('email_generated', {
                'school': school,
                'has_coach': bool(coach),
                'utr': utr,
            })
        except Exception:
            pass

        return jsonify({'email': email_text})

    except Exception as e:
        return jsonify({'error': f'AI error: {str(e)}'}), 503