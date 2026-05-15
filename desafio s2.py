import duckdb
import pandas as pd

con = duckdb.connect("sounddata.duckdb")

con.execute("""
CREATE OR REPLACE VIEW src_artistas AS
SELECT * FROM read_csv_auto('sounddata_artistas.csv');
""")

con.execute("""
CREATE OR REPLACE VIEW src_tracks AS
SELECT * FROM read_csv_auto('sounddata_tracks.csv');
""")

con.execute("""
CREATE OR REPLACE VIEW src_usuarios AS
SELECT * FROM read_csv_auto('sounddata_usuarios.csv');
""")

con.execute("""
CREATE OR REPLACE VIEW src_plays AS
SELECT * FROM read_csv_auto('sounddata_plays.csv');
""")

# Conferir se os dados carregaram corretamente
print("Usuários:", con.execute("SELECT COUNT(*) FROM dim_usuario").fetchone()[0])
print("Tracks:", con.execute("SELECT COUNT(*) FROM dim_track").fetchone()[0])
print("Artistas:", con.execute("SELECT COUNT(*) FROM dim_artista").fetchone()[0])
print("Datas:", con.execute("SELECT COUNT(*) FROM dim_data").fetchone()[0])
print("Plays:", con.execute("SELECT COUNT(*) FROM fato_plays").fetchone()[0])

# ------ criar as tabelas dimensionais------

# dim_usuario
con.execute("""
CREATE OR REPLACE TABLE dim_usuario (
    sk_usuario INTEGER PRIMARY KEY,
    usuario_id VARCHAR,
    plano VARCHAR,
    faixa_etaria VARCHAR,
    pais VARCHAR,
    cidade VARCHAR,
    dt_inicio DATE,
    dt_fim DATE,
    is_current BOOLEAN
);
""")

# dim_track
con.execute("""
CREATE OR REPLACE TABLE dim_track (
    sk_track INTEGER PRIMARY KEY,
    track_id VARCHAR,
    titulo VARCHAR,
    album VARCHAR,
    genero VARCHAR,
    duracao_total_seg INTEGER,
    explicit BOOLEAN,
    dt_inicio DATE,
    dt_fim DATE,
    is_current BOOLEAN
);
""")

# dim_artista
con.execute("""
CREATE OR REPLACE TABLE dim_artista (
    sk_artista INTEGER PRIMARY KEY,
    artista_id VARCHAR,
    nome VARCHAR,
    pais_origem VARCHAR,
    genero_prim VARCHAR,
    gravadora VARCHAR,
    dt_inicio DATE,
    dt_fim DATE,
    is_current BOOLEAN
);
""")

# dim_data
# Aqui optei por não incluir hora para evitar 
# conflito de chave primária, já que sk_data 
# será uma data no formato YYYYMMDD.
con.execute("""
CREATE OR REPLACE TABLE dim_data (
    sk_data INTEGER PRIMARY KEY,
    data_completa DATE,
    ano INTEGER,
    trimestre INTEGER,
    mes INTEGER,
    nome_mes VARCHAR,
    dia_semana INTEGER,
    nome_dia VARCHAR,
    fim_de_semana BOOLEAN
);
""")

# fato_plays
con.execute("""
CREATE OR REPLACE TABLE fato_plays (
    sk_play INTEGER PRIMARY KEY,
    sk_usuario INTEGER,
    sk_track INTEGER,
    sk_artista INTEGER,
    sk_data INTEGER,
    duracao_seg INTEGER,
    dispositivo VARCHAR,
    pais_play VARCHAR
);
""")

# ------ popular as tabelas dimensionais------
# dim_usuario
con.execute("""
INSERT INTO dim_usuario
SELECT
    row_number() OVER () AS sk_usuario,
    usuario_id,
    plano,
    faixa_etaria,
    pais,
    cidade,
    CURRENT_DATE,
    DATE '9999-12-31',
    TRUE
FROM src_usuarios;
""")

# dim_track
con.execute("""
INSERT INTO dim_track
SELECT
    row_number() OVER () AS sk_track,
    track_id,
    titulo,
    album,
    genero,
    duracao_seg AS duracao_total_seg,
    explicit,
    CURRENT_DATE,
    DATE '9999-12-31',
    TRUE
FROM src_tracks;
""")

# dim_artista
con.execute("""
INSERT INTO dim_artista
SELECT
    row_number() OVER () AS sk_artista,
    artista_id,
    nome,
    pais_origem,
    genero_prim,
    gravadora,
    CURRENT_DATE,
    DATE '9999-12-31',
    TRUE
FROM src_artistas;
""")

# dim_data
con.execute("""
INSERT INTO dim_data
SELECT DISTINCT
    CAST(strftime(CAST(play_timestamp AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data,
    CAST(play_timestamp AS DATE) AS data_completa,
    EXTRACT(YEAR FROM CAST(play_timestamp AS TIMESTAMP)) AS ano,
    EXTRACT(QUARTER FROM CAST(play_timestamp AS TIMESTAMP)) AS trimestre,
    EXTRACT(MONTH FROM CAST(play_timestamp AS TIMESTAMP)) AS mes,
    strftime(CAST(play_timestamp AS TIMESTAMP), '%B') AS nome_mes,
    EXTRACT(ISODOW FROM CAST(play_timestamp AS TIMESTAMP)) AS dia_semana,
    strftime(CAST(play_timestamp AS TIMESTAMP), '%A') AS nome_dia,
    CASE
        WHEN EXTRACT(ISODOW FROM CAST(play_timestamp AS TIMESTAMP)) IN (6, 7)
        THEN TRUE
        ELSE FALSE
    END AS fim_de_semana
FROM src_plays;
""")

# fato_plays
con.execute("""
INSERT INTO fato_plays
SELECT
    row_number() OVER () AS sk_play,
    u.sk_usuario,
    t.sk_track,
    a.sk_artista,
    CAST(strftime(CAST(p.play_timestamp AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS sk_data,
    p.duracao_seg,
    p.dispositivo,
    p.pais AS pais_play
FROM src_plays p
JOIN dim_usuario u
    ON p.usuario_id = u.usuario_id
    AND u.is_current = TRUE
JOIN dim_track t
    ON p.track_id = t.track_id
    AND t.is_current = TRUE
JOIN dim_artista a
    ON p.artista_id = a.artista_id
    AND a.is_current = TRUE;
""")

# ----validar resultados----
print("dim_usuario:", con.execute("SELECT COUNT(*) FROM dim_usuario").fetchone()[0])
print("dim_track:", con.execute("SELECT COUNT(*) FROM dim_track").fetchone()[0])
print("dim_artista:", con.execute("SELECT COUNT(*) FROM dim_artista").fetchone()[0])
print("dim_data:", con.execute("SELECT COUNT(*) FROM dim_data").fetchone()[0])
print("fato_plays:", con.execute("SELECT COUNT(*) FROM fato_plays").fetchone()[0])


# exemploo de consulta analitica
con.execute("""
SELECT
    a.nome,
    COUNT(*) AS total_plays
FROM fato_plays f
JOIN dim_artista a
    ON f.sk_artista = a.sk_artista
GROUP BY a.nome
ORDER BY total_plays DESC
LIMIT 10;
""").df()


# =========================================================
# ETAPA 3 — EXECUTANDO ANÁLISES NO STAR SCHEMA
# =========================================================

# ---------------------------------------------------------
# ANÁLISE 1 — Total de reproduções por gênero musical
# ---------------------------------------------------------
# Qual gênero possui mais plays na plataforma?

result = con.execute("""
SELECT
    t.genero,
    COUNT(*) AS total_plays
FROM fato_plays f
JOIN dim_track t
    ON f.sk_track = t.sk_track
GROUP BY t.genero
ORDER BY total_plays DESC
""")

print("Análise 1 — Total de reproduções por gênero")
print(result.df())


# ---------------------------------------------------------
# ANÁLISE 2 — Tempo médio de escuta por tipo de plano
# ---------------------------------------------------------
# Usuários de cada plano escutam, em média, quanto tempo?

result = con.execute("""
SELECT
    u.plano,
    COUNT(*) AS total_plays,
    ROUND(AVG(f.duracao_seg), 0) AS media_seg_por_play,
    ROUND(AVG(f.duracao_seg) / 60, 1) AS media_min_por_play
FROM fato_plays f
JOIN dim_usuario u
    ON f.sk_usuario = u.sk_usuario
    AND u.is_current = TRUE
GROUP BY u.plano
ORDER BY media_seg_por_play DESC
""")

print("\nAnálise 2 — Tempo médio de escuta por plano")
print(result.df())


# ---------------------------------------------------------
# ANÁLISE 3 — Top 5 artistas por ouvintes únicos
# ---------------------------------------------------------
# COUNT(DISTINCT sk_usuario) = número de usuários diferentes
# COUNT(*) = número total de reproduções

result = con.execute("""
SELECT
    a.nome AS artista,
    COUNT(DISTINCT f.sk_usuario) AS ouvintes_unicos,
    COUNT(*) AS total_plays
FROM fato_plays f
JOIN dim_artista a
    ON f.sk_artista = a.sk_artista
GROUP BY a.nome
ORDER BY ouvintes_unicos DESC, total_plays DESC
LIMIT 5
""")

print("\nAnálise 3 — Top 5 artistas por ouvintes únicos")
print(result.df())


# ---------------------------------------------------------
# ANÁLISE 4 — Reproduções por dispositivo e faixa etária
# ---------------------------------------------------------
# Em qual dispositivo cada faixa etária mais ouve música?

result = con.execute("""
SELECT
    u.faixa_etaria,
    f.dispositivo,
    COUNT(*) AS total_plays
FROM fato_plays f
JOIN dim_usuario u
    ON f.sk_usuario = u.sk_usuario
    AND u.is_current = TRUE
GROUP BY
    u.faixa_etaria,
    f.dispositivo
ORDER BY
    u.faixa_etaria,
    total_plays DESC
""")

print("\nAnálise 4 — Reproduções por dispositivo e faixa etária")
print(result.df())


#--------------------------------------------------
# Evento A: usuários mudaram de plano → SCD Tipo 2
# Função para aplicar SCD Tipo 2 em dim_usuario
#---------------------------------------------------

def aplicar_scd_usuario(usuario_id, novo_plano, data_mudanca):
    # Fecha a versão atual
    con.execute(f"""
        UPDATE dim_usuario
        SET
            dt_fim = DATE '{data_mudanca}',
            is_current = FALSE
        WHERE usuario_id = '{usuario_id}'
          AND is_current = TRUE;
    """)

    # Cria nova versão
    con.execute(f"""
        INSERT INTO dim_usuario
        SELECT
            (SELECT MAX(sk_usuario) + 1 FROM dim_usuario),
            usuario_id,
            '{novo_plano}' AS plano,
            faixa_etaria,
            pais,
            cidade,
            DATE '{data_mudanca}' AS dt_inicio,
            DATE '9999-12-31' AS dt_fim,
            TRUE AS is_current
        FROM dim_usuario
        WHERE usuario_id = '{usuario_id}'
          AND is_current = FALSE
        ORDER BY dt_fim DESC
        LIMIT 1;
    """)

# Simulando mudança de plano para um usuário
aplicar_scd_usuario('USR0042', 'premium_mensal', '2024-04-01')
aplicar_scd_usuario('USR0117', 'premium_anual', '2024-06-15')
aplicar_scd_usuario('USR0203', 'free', '2024-09-01')

# Verificar as mudanças
con.execute("""
SELECT
    sk_usuario,
    usuario_id,
    plano,
    dt_inicio,
    dt_fim,
    is_current
FROM dim_usuario
WHERE usuario_id IN ('USR0042', 'USR0117', 'USR0203')
ORDER BY usuario_id, dt_inicio;
""").df()

#----------------------------------------------------
# Evento B — artista mudou de gravadora → SCD Tipo 2
#Artista: ART0019
#Gravadora: Sony → independente
#Data: 2024-07-01
#----------------------------------------------------

# Fecha a versão atual
con.execute("""
UPDATE dim_artista
SET
    dt_fim = DATE '2024-07-01',
    is_current = FALSE
WHERE artista_id = 'ART0019'
  AND is_current = TRUE;
""")

# Cria nova versão
con.execute("""
INSERT INTO dim_artista
SELECT
    (SELECT MAX(sk_artista) + 1 FROM dim_artista),
    artista_id,
    nome,
    pais_origem,
    genero_prim,
    'independente' AS gravadora,
    DATE '2024-07-01' AS dt_inicio,
    DATE '9999-12-31' AS dt_fim,
    TRUE AS is_current
FROM dim_artista
WHERE artista_id = 'ART0019'
  AND is_current = FALSE
ORDER BY dt_fim DESC
LIMIT 1;
""")

# Verificar a mudança
con.execute("""
SELECT
    sk_artista,
    artista_id,
    nome,
    gravadora,
    dt_inicio,
    dt_fim,
    is_current
FROM dim_artista
WHERE artista_id = 'ART0019'
ORDER BY dt_inicio;
""").df()

#----------------------------------------------------
# Evento C — correção de erro no gênero do artista → SCD Tipo 1
# Mudança
#Artista: ART0031
#gênero: rock → metal
#-----------------------------------------------------

con.execute("""
UPDATE dim_artista
SET genero_prim = 'metal'
WHERE artista_id = 'ART0031';
""")

# Verificar a mudança
con.execute("""
SELECT
    artista_id,
    nome,
    genero_prim
FROM dim_artista
WHERE artista_id = 'ART0031';
""").df()

# reexecutando a análise 2
result = con.execute("""
SELECT
    u.plano,
    COUNT(*) AS total_plays,
    ROUND(AVG(f.duracao_seg), 0) AS media_seg_por_play,
    ROUND(AVG(f.duracao_seg) / 60, 1) AS media_min_por_play
FROM fato_plays f
JOIN dim_usuario u
    ON f.sk_usuario = u.sk_usuario
GROUP BY u.plano
ORDER BY media_min_por_play DESC;
""")

result.df()

# FIM!
