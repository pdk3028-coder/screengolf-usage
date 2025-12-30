import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

DB_NAME = 'screengolf.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def hash_val(val):
    """SHA-256 해시 값을 반환합니다. (주민번호 뒷자리 등에 사용)"""
    return hashlib.sha256(str(val).encode()).hexdigest()

def init_db():
    """데이터베이스 초기화 및 테이블 생성"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # 사원 명부 (로그인용)
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL UNIQUE, -- 사번
            name TEXT NOT NULL,          -- 이름
            password_hash TEXT NOT NULL, -- 비밀번호 (주민번호 뒷자리 해시)
            created_at TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # 이용 내역 (누적용)
    # 이용 내역 (누적용)
    # 스키마 변경: 시간 삭제 -> 상품명/수량 추가
    try:
        # 기존 테이블에 start_time 컬럼이 있는지 확인하고 있다면 DROP (마이그레이션)
        cursor = c.execute("PRAGMA table_info(usage_records)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'start_time' in columns:
            print("Migrating: Dropping old usage_records table...")
            c.execute("DROP TABLE usage_records")
        # item_name이 없다면(구버전) DROP (안전장치)
        elif columns and 'item_name' not in columns:
             print("Migrating: Dropping mismatch schema usage_records table...")
             c.execute("DROP TABLE usage_records")
    except Exception as e:
        print(f"Migration check failed: {e}")

    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,         -- 사번 (employees.emp_id 참조)
            usage_date TEXT NOT NULL,     -- 이용 날짜 (YYYY-MM-DD)
            item_name TEXT NOT NULL,      -- 상품명 (9홀, 18홀)
            quantity INTEGER DEFAULT 1,   -- 수량
            amount INTEGER DEFAULT 0,     -- 금액
            created_at TIMESTAMP,
            FOREIGN KEY (emp_id) REFERENCES employees (emp_id)
        )
    ''')
    
    # 시스템 설정 (관리자 비밀번호 등)
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # 기본 관리자 비밀번호 설정 (admin1234)
    # 이미 설정이 있으면 건너뜀
    c.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('admin_password', 'admin1234')")

    conn.commit()
    conn.close()
    print(f"Database {DB_NAME} initialized successfully.")

# --- 사원 관리 ---

def upsert_employee(emp_id, name, password_raw):
    """
    사원을 추가합니다. (중복 시 무시 - INSERT OR IGNORE)
    """
    conn = get_db_connection()
    c = conn.cursor()
    
    pw_hash = hash_val(password_raw)
    now = datetime.now()
    
    try:
        c.execute('''
            INSERT OR IGNORE INTO employees (emp_id, name, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (emp_id, name, pw_hash, now))
        conn.commit()
        # rowcount가 1이면 추가됨, 0이면 무시됨
        return c.rowcount > 0
    except Exception as e:
        print(f"Error inserting employee: {e}")
        return False
    finally:
        conn.close()

def upsert_employees_from_excel_file(filepath):
    """
    엑셀 파일을 읽어 사원을 일괄 등록합니다.
    gift_project의 로직(인덱스 기반, 데이터 정제)을 그대로 이식하여 호환성을 확보합니다.
    중복된 사원은 제외하고(SKIP) 신규 사원만 등록합니다.
    """
    try:
        # V11: dtype=str to preserve leading zeros
        df = pd.read_excel(filepath, dtype=str)
        
        # Helper to safe access by iloc
        def get_col_data(col_idx):
            if col_idx < len(df.columns):
                return df.iloc[:, col_idx]
            return None

        # Function to clean typical Excel numeric artifacts
        def clean_str(series):
            if series is None:
                return pd.Series([''] * len(df))
                
            def convert_val(x):
                s = str(x).strip()
                if s.lower() in ['nan', 'none', '', 'nat']:
                    return ''
                if s.endswith('.0'):
                    return s[:-2]
                return s
                    
            return series.apply(convert_val)

        # gift_project와 동일한 컬럼 인덱스 매핑
        # 사번: 11, 이름: 12, 주민번호뒷자리(비밀번호): 26
        emp_ids = clean_str(get_col_data(11))
        names = clean_str(get_col_data(12))
        passwords = clean_str(get_col_data(26))
        
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.now()
        count = 0
        
        for i in range(len(df)):
            emp_id = emp_ids[i]
            name = names[i]
            password = passwords[i]
            
            if not emp_id or not name:
                continue
            
            if not password: 
                continue

            pw_hash = hash_val(password)
            
            c.execute('''
                INSERT OR IGNORE INTO employees (emp_id, name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
            ''', (emp_id, name, pw_hash, now))
            
            if c.rowcount > 0:
                count += 1
            
        conn.commit()
        conn.close()
        return count, "성공"
        
    except Exception as e:
        return 0, f"오류 발생: {str(e)}"

def get_employee(emp_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    return user

def verify_user(emp_id, password_raw):
    """로그인 인증: 사번과 비밀번호(주민번호 뒷자리) 확인"""
    user = get_employee(emp_id)
    if user:
        input_hash = hash_val(password_raw)
        if user['password_hash'] == input_hash:
            return user
    return None

def get_all_employees():
    """모든 사원 목록 반환 (관리자용)"""
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM employees ORDER BY emp_id').fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- 이용 내역 관리 ---

def add_usage_record(emp_id, usage_date, item_name, quantity, amount):
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO usage_records (emp_id, usage_date, item_name, quantity, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (emp_id, usage_date, item_name, quantity, amount, datetime.now()))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding usage record: {e}")
        return False
    finally:
        conn.close()

def get_usage_records(emp_id=None, limit=100):
    """
    이용 내역 조회. 
    emp_id가 있으면 해당 사원만, 없으면 전체(관리자용, 최신순).
    """
    conn = get_db_connection()
    query = '''
        SELECT r.*, e.name 
        FROM usage_records r
        LEFT JOIN employees e ON r.emp_id = e.emp_id
    '''
    params = []
    
    if emp_id:
        query += ' WHERE r.emp_id = ?'
        params.append(emp_id)
        
    query += ' ORDER BY r.usage_date DESC, r.created_at DESC LIMIT ?'
    params.append(limit)
    
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_usage_record(record_id, emp_id):
    """특정 이용 내역 삭제 (본인 확인 포함)"""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # 본인의 글인지 확인하고 삭제
        c.execute("DELETE FROM usage_records WHERE id = ? AND emp_id = ?", (record_id, emp_id))
        conn.commit()
        return c.rowcount > 0 # 삭제된 행이 있으면 True
    except Exception as e:
        print(f"Error deleting record: {e}")
        return False
    finally:
        conn.close()

def get_all_usage_records_df():
    """전체 이용 내역을 DataFrame으로 반환 (엑셀 다운로드용)"""
    conn = get_db_connection()
    query = '''
        SELECT 
            r.usage_date as "이용일자", 
            e.emp_id as "사번", 
            e.name as "이름",
            r.item_name as "상품명", 
            r.quantity as "수량", 
            r.amount as "금액", 
            r.created_at as "등록일시"
        FROM usage_records r
        LEFT JOIN employees e ON r.emp_id = e.emp_id
        ORDER BY r.usage_date DESC, r.created_at DESC
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# --- 설정 관리 ---

def get_setting(key, default=None):
    conn = get_db_connection()
    row = conn.execute('SELECT value FROM system_settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
