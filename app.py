from flask import Flask; app=Flask(__name__)
@app.route('/')
def home():
    return open('index.html', encoding='utf-8').read()
if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000)
