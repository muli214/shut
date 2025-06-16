from flask import Flask, send_from_directory, render_template_string

app = Flask(__name__, static_folder='static')

# Serve the main HTML page from /static
@app.route('/')
def index():
    with open('static/qa_page_dynamic.html', encoding='utf-8') as f:
        return render_template_string(f.read())

# Serve any files under /data (like qa_pairs.json)
@app.route('/data/<path:filename>')
def serve_data(filename):
    return send_from_directory('data', filename)

if __name__ == '__main__':
    # Run the Flask server on port 8080 and allow external access (e.g. in Codespaces)
    app.run(host='0.0.0.0', port=8080)
