# CogniType 🧠⌨️
**Typing Biometrics & Cognitive Load Analyzer**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Backend-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)](https://www.sqlite.org/)

CogniType is a web-based psychometrics research platform designed to bridge behavioral data collection and machine learning. By capturing continuous, millisecond-level keystroke dynamics (dwell time and flight time), the system extracts objective motor-execution biomarkers to analyze cognitive load, mental fatigue, and dual-task interference.

## 🚀 Core Features
* **High-Resolution Data Capture:** Utilizes the sub-millisecond `performance.now()` API to track independent key states, accurately logging overlapping keystrokes and flight time latency.
* **Neurological Hesitation Heatmaps:** Translates historical latency vectors into dynamic UI visualizations, mapping localized motor fatigue and cognitive friction directly onto a virtual keyboard.
* **Dual-Task Psychometric Analytics:** Generates session-level behavioral profiles mapping dwell vs. flight time variance, enabling the mathematical modeling of automaticity versus active cognitive struggle.
* **Scalable Data Pipeline:** Built with Flask and SQLAlchemy, designed to log high-volume sequential event arrays for downstream ETL and feature engineering.

---

## 🛠️ Tech Stack
* **Backend:** Python, Flask, SQLAlchemy
* **Frontend:** HTML5, CSS3, Bootstrap 5, JavaScript (ES6)
* **Visualization:** Chart.js, Jinja2 Template Engine
* **Database:** SQLite (MVP) / PostgreSQL Ready

---

## ⚙️ Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/amanmauryas/CogniType.git](https://github.com/amanmauryas/CogniType.git)
   cd CogniType