from boltiotai import openai
import os
import json
from flask import (
    Flask,
    render_template_string,
    request,
    jsonify,
    session,
    redirect,
    url_for,
)

# ========================
# OpenAI / BoltIOT config
# ========================
openai.api_key = os.environ.get("OPENAI_API_KEY", "")

# ========================
# Flask app config
# ========================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")

SYSTEM_PROMPT = (
    "You are an expert educational assistant. Generate a multiple-choice quiz based on the given topic. "
    "Each question should have exactly 4 options and one correct answer. "
    "Output STRICT JSON with this schema: "
    '{"questions": [{"q": "question text", "options": ["A", "B", "C", "D"], "answer_index": 0}]}'
)

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def call_model(topic, num_questions):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Generate a {num_questions}-question quiz on the topic: {topic}",
        },
    ]

    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
    )

    # Be tolerant to BoltIOT/OpenAI SDK differences
    try:
        content = response.choices[0].message.content
    except (AttributeError, KeyError, TypeError):
        content = response["choices"][0]["message"]["content"]

    return content.strip()


@app.route("/", methods=["GET"])
def home():
    return render_template_string(TEMPLATE, quiz=None, result=None, letters=LETTERS)


@app.route("/generate", methods=["POST"])
def generate():
    topic = request.form.get("topic", "").strip()
    num_questions = request.form.get("num_questions", "5")
    try:
        num_questions = max(1, min(20, int(num_questions)))
    except ValueError:
        num_questions = 5

    if not topic:
        return jsonify({"error": "Please enter a valid topic."}), 400

    try:
        quiz_json = call_model(topic, num_questions)
        print("RAW MODEL OUTPUT:\n", quiz_json)  # debug log
        try:
            quiz_data = json.loads(quiz_json)
        except json.JSONDecodeError as e:
            return jsonify(
                {"error": f"JSON parsing failed: {e}", "raw": quiz_json}
            ), 500

        session["quiz"] = quiz_data
        return render_template_string(
            TEMPLATE, quiz=quiz_data, result=None, letters=LETTERS
        )
    except Exception as e:
        return jsonify({"error": f"Model error: {e}"}), 500


@app.route("/submit", methods=["POST"])
def submit():
    quiz = session.get("quiz")
    if not quiz:
        return redirect(url_for("home"))

    questions = quiz.get("questions", [])
    score = 0
    results = []

    for i, q in enumerate(questions):
        correct_index = q.get("answer_index")
        user_index = request.form.get(f"q{i}")
        try:
            user_index = int(user_index)
        except (TypeError, ValueError):
            user_index = None

        is_correct = user_index == correct_index
        if is_correct:
            score += 1
        results.append(
            {
                "question": q.get("q"),
                "options": q.get("options"),
                "correct": correct_index,
                "selected": user_index,
                "is_correct": is_correct,
            }
        )

    return render_template_string(
        TEMPLATE,
        quiz=None,
        result={"score": score, "total": len(questions), "details": results},
        letters=LETTERS,
    )


TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dynamic Quiz Generator</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container py-5">
    <h1 class="text-center mb-4 text-primary">📝 Dynamic Quiz Generator</h1>
    {% if not quiz and not result %}
      <form method="POST" action="/generate">
        <div class="mb-3">
          <label for="topic" class="form-label">Enter a Topic:</label>
          <input type="text" class="form-control" name="topic" placeholder="e.g., Python Basics" required>
        </div>
        <div class="mb-3">
          <label for="num_questions" class="form-label">Number of Questions (1-20):</label>
          <input type="number" class="form-control" name="num_questions" min="1" max="20" value="5" required>
        </div>
        <button type="submit" class="btn btn-primary">Generate Quiz</button>
      </form>
    {% endif %}

    {% if quiz %}
    <form method="POST" action="/submit" class="mt-4">
      {% for q in quiz.questions %}
        {% set q_index = loop.index0 %}
        <div class="mb-3">
          <p><strong>{{ loop.index }}. {{ q.q }}</strong></p>
          {% for opt in q.options %}
            {% set o_index = loop.index0 %}
            <div class="form-check">
              <input class="form-check-input" type="radio" name="q{{ q_index }}" id="q{{ q_index }}_{{ o_index }}" value="{{ o_index }}" required>
              <label class="form-check-label" for="q{{ q_index }}_{{ o_index }}">{{ opt }}</label>
            </div>
          {% endfor %}
        </div>
      {% endfor %}
      <button type="submit" class="btn btn-success">Submit Quiz</button>
    </form>
    {% endif %}

    {% if result %}
      <div class="card mt-4">
        <div class="card-body">
          <h4 class="text-success">Your Score: {{ result.score }}/{{ result.total }}</h4>
          <ul class="list-group mt-3">
            {% for r in result.details %}
              <li class="list-group-item">
                <strong>{{ loop.index }}. {{ r.question }}</strong><br>
                {% for opt in r.options %}
                  {% set opt_index = loop.index0 %}
                  <span class="d-block {% if opt_index == r.correct %}text-success{% elif opt_index == r.selected and not r.is_correct %}text-danger{% endif %}">
                    {{ letters[opt_index] }}. {{ opt }}
                    {% if opt_index == r.correct %} <strong>(Correct)</strong>{% endif %}
                    {% if opt_index == r.selected and not r.is_correct %} <strong>(Your choice)</strong>{% endif %}
                  </span>
                {% endfor %}
              </li>
            {% endfor %}
          </ul>
          <a href="/" class="btn btn-outline-primary mt-3">Take Another Quiz</a>
        </div>
      </div>
    {% endif %}
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
# updated code
