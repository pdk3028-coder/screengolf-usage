from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
import os
import database
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO

app = Flask(__name__)
# 보안: 환경 변수에서 SECRET_KEY를 가져오거나 기본값 사용 (배포 시 필수 변경)
app.secret_key = os.environ.get('SECRET_KEY', 'screengolf_secret_key')
app.permanent_session_lifetime = timedelta(minutes=60)

# DB 초기화
database.init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    emp_id = request.form.get('emp_id')
    password = request.form.get('password') # 사용자가 입력한 주민번호 뒷자리
    
    user = database.verify_user(emp_id, password)
    
    if user:
        session['user_id'] = user['emp_id']
        session['user_name'] = user['name']
        return redirect(url_for('dashboard'))
    else:
        # gift_project 스타일의 에러 메시지
        flash('아이디 또는 비밀번호가 일치하지 않습니다.', 'error')
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        emp_id = request.form.get('emp_id')
        
        if database.reset_password_to_default(emp_id):
            flash(f'비밀번호가 초기화되었습니다. (초기 비밀번호: {emp_id})', 'success')
            return redirect(url_for('index'))
        else:
            flash('존재하지 않는 아이디(사번)입니다.', 'error')
            
    return render_template('reset_password.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    emp_id = session['user_id']
    user_name = session['user_name']
    
    # 최근 내역 조회 (최신 10건만)
    records = database.get_usage_records(emp_id, limit=10)
    
    # 초기 비밀번호(사번) 사용 여부 확인
    is_default_pw = False
    if database.verify_user(emp_id, emp_id):
        is_default_pw = True
    
    return render_template('dashboard.html', name=user_name, records=records, show_pw_warning=is_default_pw)


        
@app.route('/api/record', methods=['POST'])
def add_record():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    
    emp_id = session['user_id']
    
    try:
        # JSON 데이터 수신
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '데이터가 없습니다.'}), 400
            
        usage_date = data.get('usage_date')
        cart = data.get('cart', []) # [{'item_name': '9홀', 'quantity': 1, 'price': 2000}, ...]
        
        if not usage_date or not cart:
            return jsonify({'success': False, 'message': '날짜 또는 상품이 선택되지 않았습니다.'}), 400
            
        count = 0
        for item in cart:
            item_name = item.get('item_name')
            quantity = int(item.get('quantity', 0))
            price = int(item.get('price', 0))
            amount = price * quantity
            
            if item_name and quantity > 0:
                database.add_usage_record(emp_id, usage_date, item_name, quantity, amount)
                count += 1
        
        if count > 0:
            return jsonify({'success': True, 'message': f'{count}건의 이용 내역이 등록되었습니다.'})
        else:
            return jsonify({'success': False, 'message': '등록할 유효한 상품이 없습니다.'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    
    emp_id = session['user_id']
    
    if database.delete_usage_record(record_id, emp_id):
        return jsonify({'success': True, 'message': '이용 내역이 삭제되었습니다.'})
        return jsonify({'success': False, 'message': '삭제 실패: 존재하지 않거나 권한이 없습니다.'})

@app.route('/api/history')
def get_user_history():
    """사용자의 전체 이용 내역 조회 API"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
    
    emp_id = session['user_id']
    # 전체 내역 조회 (충분히 큰 수로 limit 설정)
    records = database.get_usage_records(emp_id, limit=10000)
    return jsonify({'success': True, 'data': records})

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        emp_id = session['user_id']
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 현재 비밀번호 확인 (보안 강화)
        if not database.verify_user(emp_id, current_password):
             flash('현재 비밀번호가 일치하지 않습니다.', 'error')
             return render_template('change_password.html')

        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('change_password.html')
            
        if database.update_password(emp_id, new_password):
            flash('비밀번호가 성공적으로 변경되었습니다.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
            
    return render_template('change_password.html')

# --- 관리자 페이지 ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        real_pw = database.get_setting('admin_password', 'admin1234')
        
        if password == real_pw:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('관리자 비밀번호가 틀렸습니다.', 'error')
            
    return render_template('admin_login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    # 최근 100건 조회
    records = database.get_usage_records(limit=100)
    return render_template('admin.html', records=records)

@app.route('/admin/upload_employees', methods=['POST'])
def admin_upload_employees():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    if 'file' not in request.files:
        flash('파일이 없습니다.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    file = request.files['file']
    if file.filename == '':
        flash('선택된 파일이 없습니다.', 'error')
        return redirect(url_for('admin_dashboard'))
        
    if file:
        filename = "temp_employees.xlsx"
        file.save(filename)
        
        count, msg = database.upsert_employees_from_excel_file(filename)
        if count > 0:
            flash(f'{count}명의 사원 정보가 업데이트되었습니다.', 'success')
        else:
            flash(f'업데이트 실패: {msg}', 'error')
            
    return redirect(url_for('admin_dashboard'))

@app.route('/api/admin/bulk_add', methods=['POST'])
def admin_bulk_add():
    """엑셀 붙여넣기 데이터 처리 (JSON)"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.json.get('data', []) # [{'emp_id': '...', 'name': '...', 'password': '...'}, ...]
        count = 0
        for item in data:
            if item.get('emp_id') and item.get('name'):
                # password가 없으면 None 전달 -> database에서 처리
                password = item.get('password')
                if database.upsert_employee(item['emp_id'], item['name'], password):
                    count += 1
        
        return jsonify({'success': True, 'count': count, 'message': f'{count}명 등록 완료'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/reset', methods=['POST'])
def admin_reset_data():
    """관리자 데이터 초기화 API"""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    success, msg = database.reset_all_data()
    return jsonify({'success': success, 'message': msg})

@app.route('/admin/download')
def admin_download():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    df = database.get_all_usage_records_df()
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='이용내역')
    output.seek(0)
    
    filename = f"ScreenGolf_Usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
