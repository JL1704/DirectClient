import mysql.connector
import random
from datetime import datetime, timedelta
from math import factorial

# ---------- CREAR BASE DE DATOS INESTABLE ----------

def crear_base_datos():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="call_center"
    )
    cursor = conn.cursor()

    # Reiniciar tablas
    cursor.execute("DROP TABLE IF EXISTS call_assignments")
    cursor.execute("DROP TABLE IF EXISTS calls")
    cursor.execute("DROP TABLE IF EXISTS agent_skills")
    cursor.execute("DROP TABLE IF EXISTS system_parameters")
    cursor.execute("DROP TABLE IF EXISTS skills")
    cursor.execute("DROP TABLE IF EXISTS agents")

    # Crear tablas
    cursor.execute("""CREATE TABLE agents (
        agent_id INT PRIMARY KEY, name VARCHAR(255) NOT NULL)""")
    cursor.execute("""CREATE TABLE skills (
        skill_id INT PRIMARY KEY, name VARCHAR(255) NOT NULL)""")
    cursor.execute("""CREATE TABLE agent_skills (
        agent_id INT, skill_id INT,
        PRIMARY KEY (agent_id, skill_id),
        FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id))""")
    cursor.execute("""CREATE TABLE calls (
        call_id INT PRIMARY KEY, skill_id INT,
        arrival_time DATETIME NOT NULL,
        service_start_time DATETIME,
        service_end_time DATETIME,
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id))""")
    cursor.execute("""CREATE TABLE call_assignments (
        call_id INT PRIMARY KEY, agent_id INT,
        FOREIGN KEY (call_id) REFERENCES calls(call_id),
        FOREIGN KEY (agent_id) REFERENCES agents(agent_id))""")
    cursor.execute("""CREATE TABLE system_parameters (
        skill_id INT PRIMARY KEY, arrival_rate FLOAT, service_rate FLOAT,
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id))""")

    # Insertar agentes y habilidades
    agents = [(1, "Agente A"), (2, "Agente B"), (3, "Agente C"), (4, "Agente D")]
    cursor.executemany("INSERT INTO agents VALUES (%s, %s)", agents)
    skills = [(1, "Ventas"), (2, "Soporte Técnico"), (3, "Consultas Generales")]
    cursor.executemany("INSERT INTO skills VALUES (%s, %s)", skills)
    agent_skills = [
        (1, 1), (1, 2),
        (2, 2), (2, 3),
        (3, 1), (3, 2), (3, 3),
        (4, 3)
    ]
    cursor.executemany("INSERT INTO agent_skills VALUES (%s, %s)", agent_skills)

    # Tasa de llegada alta → sistema inestable
    system_params = [
        (1, 60, 20),  # Ventas → 2 agentes → ρ = 60 / (2*20) = 1.5
        (2, 60, 25),  # Soporte → 3 agentes → ρ = 60 / 75 = 0.8 (estable)
        (3, 60, 36)   # Consultas → 3 agentes → ρ ≈ 0.56 (estable)
    ]
    cursor.executemany("INSERT INTO system_parameters VALUES (%s, %s, %s)", system_params)

    # Insertar llamadas
    call_id = 1
    start_date = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

    for day in range(14):  # 2 semanas
        day_start = start_date + timedelta(days=day)
        for hour in range(8):  # de 09:00 a 17:00
            for minute in range(60):
                for _ in range(5):  # 5 llamadas por minuto
                    skill_id = random.choices([1, 2, 3], weights=[0.33, 0.34, 0.33])[0]
                    arrival_time = day_start + timedelta(hours=hour, minutes=minute, seconds=random.randint(0, 59))
                    service_rate = next(s[2] for s in system_params if s[0] == skill_id)
                    avg_service_time = 60 / service_rate
                    actual_service_time = timedelta(minutes=random.expovariate(1 / avg_service_time))
                    service_start = arrival_time + timedelta(minutes=random.uniform(3, 6))
                    service_end = service_start + actual_service_time

                    cursor.execute("INSERT INTO calls VALUES (%s, %s, %s, %s, %s)",
                                   (call_id, skill_id, arrival_time, service_start, service_end))
                    cursor.execute("SELECT agent_id FROM agent_skills WHERE skill_id = %s", (skill_id,))
                    assigned_agent = random.choice([row[0] for row in cursor.fetchall()])
                    cursor.execute("INSERT INTO call_assignments VALUES (%s, %s)", (call_id, assigned_agent))
                    call_id += 1

    conn.commit()
    cursor.close()
    conn.close()


# ---------- FUNCIONES DE TEORÍA DE COLAS M/M/c ----------

def calcular_p0(lambd, mu, c):
    rho = lambd / (c * mu)
    suma = sum((lambd / mu)**n / factorial(n) for n in range(c))
    parte_final = ((lambd / mu)**c / (factorial(c) * (1 - rho))) if rho < 1 else float('inf')
    return 1 / (suma + parte_final)

def calcular_Lq(p0, lambd, mu, c):
    rho = lambd / (c * mu)
    if rho >= 1:
        return float('inf')
    return (p0 * ((lambd / mu)**c) * rho) / (factorial(c) * ((1 - rho)**2))

def calcular_metricas(lambd, mu, c):
    rho = lambd / (c * mu)
    p0 = calcular_p0(lambd, mu, c)
    Lq = calcular_Lq(p0, lambd, mu, c)
    Wq = Lq / lambd
    W = Wq + (1 / mu)
    L = lambd * W
    insatisfecho = W > 10
    return {
        'λ': lambd, 'μ': mu, 'c': c,
        'ρ': round(rho, 4), 'P₀': round(p0, 4),
        'Lq': round(Lq, 2), 'Wq (min)': round(Wq, 2),
        'W (min)': round(W, 2), 'L': round(L, 2),
        'Cliente insatisfecho': 'Sí' if insatisfecho else 'No'
    }


# ---------- CALCULAR MÉTRICAS Y ESTABILIZAR ----------

def imprimir_metricas():
    global llamadas_por_tipo, params, servidores_por_tipo

    cursor = conn.cursor(dictionary=True)

    # Calcular horas laborales totales
    total_horas = 14 * 8  # 2 semanas * 8 horas

    # Obtener total de llamadas por tipo
    cursor.execute("""
        SELECT skill_id, COUNT(*) AS total_llamadas
        FROM calls GROUP BY skill_id
    """)
    llamadas_por_tipo = {
        row['skill_id']: row['total_llamadas'] / total_horas  # λ promedio por hora
        for row in cursor.fetchall()
    }

    # Parámetros del sistema y servidores disponibles
    cursor.execute("SELECT * FROM system_parameters")
    params = {row['skill_id']: (row['arrival_rate'], row['service_rate']) for row in cursor.fetchall()}
    cursor.execute("SELECT skill_id, COUNT(*) AS servidores FROM agent_skills GROUP BY skill_id")
    servidores_por_tipo = {row['skill_id']: row['servidores'] for row in cursor.fetchall()}

    # Cálculo de métricas por tipo de llamada
    for skill_id, lambd in llamadas_por_tipo.items():
        mu = params[skill_id][1]
        c = servidores_por_tipo[skill_id]
        resultado = calcular_metricas(lambd, mu, c)
        nombre = {1: "Ventas", 2: "Soporte Técnico", 3: "Consultas Generales"}[skill_id]
        print(f"\n--- {nombre} ---")
        for k, v in resultado.items():
            print(f"{k}: {v}")

    cursor.close()



def estabilizar_sistema():
    print("\n=== ESTABILIZACIÓN DEL SISTEMA ===")
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(agent_id) FROM agents")
    max_id = cursor.fetchone()[0] or 0
    new_agent_id = max_id + 1
    extra_count = 1

    for skill_id in [1, 2, 3]:
        lambd = llamadas_por_tipo.get(skill_id, 0)
        mu = params[skill_id][1]
        c_actual = servidores_por_tipo.get(skill_id, 0)
        rho = lambd / (c_actual * mu)
        if rho >= 1:
            c_requerido = int((lambd / mu) + 1)
            nuevos = c_requerido - c_actual
            for _ in range(nuevos):
                name = f"Agente Extra {extra_count}"
                cursor.execute("INSERT INTO agents (agent_id, name) VALUES (%s, %s)", (new_agent_id, name))
                cursor.execute("INSERT INTO agent_skills (agent_id, skill_id) VALUES (%s, %s)", (new_agent_id, skill_id))
                print(f"🛠 '{name}' agregado con habilidad en {['Ventas', 'Soporte Técnico', 'Consultas Generales'][skill_id-1]}")
                new_agent_id += 1
                extra_count += 1

    conn.commit()
    cursor.close()
    print("✅ Sistema estabilizado.")


# ---------- EJECUCIÓN DEL PROGRAMA COMPLETO ----------

crear_base_datos()

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="diana25",
    database="call_center"
)

print("\n=== MÉTRICAS PROMEDIO (ANTES DE ESTABILIZAR) ===")
imprimir_metricas()

estabilizar_sistema()

print("\n=== MÉTRICAS PROMEDIO (DESPUÉS DE ESTABILIZAR) ===")
imprimir_metricas()

conn.close()

