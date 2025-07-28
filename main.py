from boltiotai import openai
import os
import json
import re
from flask import Flask, render_template_string, request, session, redirect, url_for

# ========================
# OpenAI / BoltIOT config
# ========================
openai.api_key = os.environ.get('OPENAI_API_KEY', '')

# ========================
# Flask app config
# ========================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

SYSTEM_PROMPT = (
    "You are an expert question setter. Generate high-quality, unambiguous multiple-choice "
    "questions. Output STRICTLY valid JSON that can be parsed by Python's json.loads(). "
    "Do not include markdown code fences."
)

USER_PROMPT_TEMPLATE = (
    "Create a quiz for the topic: '{topic}'.\n"
    "Difficulty: {difficulty}.\n"
    "Number of questions: {num_questions}.\n\n"
    "Return STRICT JSON with this exact schema:\n"
    "{\n"
    "  \"questions\": [\n"
    "    {\n"
    "      \"q\": \"<question text>\",\n"
    "      \"options\": [\"A\", \"B\", \"C\", \"D\"],\n"
    "      \"answer_index\": <0-based index of correct option>,\n"
    "      \"explanation\": \"<1-2 line explanation>\"\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- EXACTLY {num_questions} items in 'questions'.\n"
    "- Every question MUST have exactly 4 options.\n"
    "- 'answer_index' MUST be an integer 0-3.\n"
    "- No markdown, no backticks, no commentary outside JSON."
)


def call_quiz_model(topic: str, num_questions: int, difficulty: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
            topic=topic, num_questions=num_questions, difficulty=difficulty
        )}
    ]
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.4,
    )
    raw = resp.choices[0].message.content.strip()
    return parse_strict_json(raw)


def parse_strict_json(txt: str):
    """Try to coerce the model output into valid JSON by clipping to outermost braces."""
    # Find first '{' and last '}' to reduce chance of trailing commentary
    start = txt.find('{')
    end = txt.rfind('}')
    if start != -1 and end != -1:
        txt = txt[start:end+1]
    return json.loads(txt)


@app.route('/', methods=['GET'])
def home():
    return render_template_string(FORM_TMPL)


@app.route('/generate', methods=['POST'])
def generate():
    topic = request.form.get('topic', '').strip()
    difficulty = request.form.get('difficulty', 'Medium')
    num = request.form.get('num_questions', '5')
    try:
        num = int(num)
        if num < 1 or num > 20:
            raise ValueError
    except ValueError:
        num = 5

    if not topic:
        topic = "General Knowledge"

    try:
        data = call_quiz_model(topic, num, difficulty)
        session['quiz'] = data
        session['meta'] = {'topic': topic, 'difficulty': difficulty}
        return redirect(url_for('quiz'))
    except Exception as e:
        return render_template_string(ERROR_TMPL, error=str(e))


@app.route('/quiz', methods=['GET'])
def quiz():
    quiz = session.get('quiz')
    meta = session.get('meta')
    if not quiz:
        return redirect(url_for('home'))
    return render_template_string(QUIZ_TMPL, quiz=quiz, meta=meta)


@app.route('/submit', methods=['POST'])
def submit():
    quiz = session.get('quiz')
    meta = session.get('meta')
    if not quiz:
        return redirect(url_for('home'))

    questions = quiz.get('questions', [])
    user_answers = []
    score = 0
    results = []

    for i, q in enumerate(questions):
        correct_idx = q.get('answer_index')
        user_choice = request.form.get(f'q{i}')
        try:
            user_choice = int(user_choice) if user_choice is not None else None
        except ValueError:
            user_choice = None

        is_correct = (user_choice == correct_idx)
        if is_correct:
            score += 1
        results.append({
            'q': q.get('q'),
            'options': q.get('options', []),
            'correct_idx': correct_idx,
            'user_idx': user_choice,
            'explanation': q.get('explanation', ''),
            'is_correct': is_correct,
        })

    return render_template_string(RESULT_TMPL, score=score, total=len(questions), results=results, meta=meta)


FORM_TMPL = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dynamic Quiz Generator</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    body { background: radial-gradient(circle at 10% 20%, #eef2ff 0%, #e0e7ff 50%, #c7d2fe 100%); min-height: 100vh; }
    .glass-card { background: rgba(255, 255, 255, 0.6); backdrop-filter: blur(14px) saturate(160%); border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 1.5rem; }
  </style>
</head>
<body>
  <div class="container py-5">
    <h1 class="mb-4 text-primary">🧠 Dynamic Quiz Generator</h1>
    <div class="glass-card">
      <form action="/generate" method="POST">
        <div class="mb-3">
          <label class="form-label">Topic</label>
          <input type="text" name="topic" class="form-control" placeholder="e.g. Object Oriented Programming in Java" required />
        </div>
        <div class="row">
          <div class="col-md-4 mb-3">
            <label class="form-label">Difficulty</label>
            <select name="difficulty" class="form-select">
              <option>Easy</option>
              <option selected>Medium</option>
              <option>Hard</option>
            </select>
          </div>
          <div class="col-md-4 mb-3">
          <label class="form-label">Number of Questions (1-20)</label>
          <input type="number" min="1" max="20" value="5" name="num_questions" class="form-control" required />
        </div>
        </div>
        <div class="d-flex justify-content-end">
          <button type="submit" class="btn btn-primary">Generate Quiz</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
"""


QUIZ_TMPL = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Take Quiz</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    body { background: radial-gradient(circle at 10% 20%, #eef2ff 0%, #e0e7ff 50%, #c7d2fe 100%); min-height: 100vh; }
    .glass-card { background: rgba(255, 255, 255, 0.6); backdrop-filter: blur(14px) saturate(160%); border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 1.5rem; }
    .question { margin-bottom: 1.25rem; }
  </style>
</head>
<body>
  <div class="container py-5">
    <h1 class="mb-2 text-primary">📝 Quiz</h1>
    <p class="text-muted">Topic: <strong>{{ meta.topic }}</strong> · Difficulty: <strong>{{ meta.difficulty }}</strong></p>
    <form action="/submit" method="POST" class="glass-card">
      {% for q in quiz.questions %}
        <div class="question">
          <p class="fw-semibold">{{ loop.index }}. {{ q.q }}</p>
          {% for opt in q.options %}
            <div class="form-check">
              <input class="form-check-input" type="radio" name="q{{ loop.parent.index0 }}" id="q{{ loop.parent.index0 }}_{{ loop.index0 }}" value="{{ loop.index0 }}" required>
              <label class="form-check-label" for="q{{ loop.parent.index0 }}_{{ loop.index0 }}">{{ opt }}</label>
            </div>
          {% endfor %}
        </div>
        <hr/>
      {% endfor %}
      <div class="d-flex justify-content-end">
        <button class="btn btn-success" type="submit">Submit</button>
      </div>
    </form>
  </div>
</body>
</html>
"""


RESULT_TMPL = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Results</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    body { background: radial-gradient(circle at 10% 20%, #eef2ff 0%, #e0e7ff 50%, #c7d2fe 100%); min-height: 100vh; }
    .glass-card { background: rgba(255, 255, 255, 0.6); backdrop-filter: blur(14px) saturate(160%); border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 1.5rem; }
    .correct { color: #16a34a; }
    .wrong { color: #dc2626; }
  </style>
</head>
<body>
  <div class="container py-5">
    <h1 class="mb-3 text-primary">📊 Your Score</h1>
    <div class="glass-card mb-4">
      <h4>Score: {{ score }}/{{ total }}</h4>
      <p class="text-muted">Topic: <strong>{{ meta.topic }}</strong> · Difficulty: <strong>{{ meta.difficulty }}</strong></p>
      <a href="/" class="btn btn-outline-primary btn-sm">Generate New Quiz</a>
    </div>

    {% for r in results %}
      <div class="glass-card mb-3">
        <p class="fw-semibold">{{ loop.index }}. {{ r.q }}</p>
        <ul>
          {% for opt in r.options %}
            <li
              class="{% if loop.index0 == r.correct_idx %}correct{% endif %}{% if r.user_idx == loop.index0 and not r.is_correct %} wrong{% endif %}">
              {{ opt }}
              {% if loop.index0 == r.correct_idx %} <strong>(Correct)</strong>{% endif %}
              {% if r.user_idx == loop.index0 and not r.is_correct %} <strong>(Your choice)</strong>{% endif %}
            </li>
          {% endfor %}
        </ul>
        <p><em>Explanation:</em> {{ r.explanation }}</p>
      </div>
    {% endfor %}
  </div>
</body>
</html>
"""


ERROR_TMPL = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Error</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" />
</head>
<body>
  <div class="container py-5">
    <h1 class="text-danger">Error</h1>
    <p>{{ error }}</p>
    <a href="/" class="btn btn-primary">Back</a>
  </div>
</body>
</html>
"""


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
