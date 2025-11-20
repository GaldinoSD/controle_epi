# -*- coding: utf-8 -*-
from flask import (
    Flask, render_template, redirect, url_for, request,
    flash, make_response, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from datetime import datetime, date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
import sqlite3
import os

# ============================
# CONFIGURAÇÃO INICIAL DO APP
# ============================
app = Flask(__name__)
app.config.from_object('config.Config')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# ============================
# MODELOS
# ============================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120))
    login = db.Column(db.String(80), unique=True)
    senha = db.Column(db.String(120))
    role = db.Column(db.String(50), default='user')  # admin / supervisor / user


# ============================
# EPI
# ============================
class Epi(db.Model):
    __tablename__ = 'epi'

    id = db.Column(db.Integer, primary_key=True)

    # campos existentes
    nome = db.Column(db.String(120), nullable=False)
    numero_ca = db.Column(db.String(50))
    validade_ca = db.Column(db.String(50))  # formato BR DD/MM/YYYY
    quantidade = db.Column(db.Integer, default=0)

    # 🔥 novos campos
    codigo_produto = db.Column(db.String(50))
    observacao = db.Column(db.String(255))

    # relação com entregas
    entregas = db.relationship(
        'EntregaEpi',
        backref='epi',
        lazy=True,
        cascade='all, delete-orphan'
    )

    # relação com histórico (novo)
    historico = db.relationship(
        "HistoricoEpi",
        backref="epi_rel",
        lazy=True,
        cascade='all, delete-orphan'
    )


# ============================
# FUNCIONÁRIO
# ============================
class Funcionario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    matricula = db.Column(db.String(50), unique=True, nullable=False)
    setor = db.Column(db.String(120))
    data_admissao = db.Column(db.Date)
    senha_validacao = db.Column(db.String(120))

    entregas = db.relationship(
        'EntregaEpi',
        backref='funcionario',
        lazy=True,
        cascade='all, delete-orphan'
    )


# ============================
# ENTREGA DE EPI
# ============================
class EntregaEpi(db.Model):
    __tablename__ = 'entrega_epi'

    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id', ondelete='CASCADE'), nullable=False)
    epi_id = db.Column(db.Integer, db.ForeignKey('epi.id', ondelete='CASCADE'), nullable=False)
    
    quantidade = db.Column(db.Integer, nullable=False)
    data_entrega = db.Column(db.DateTime, default=datetime.utcnow)
    validade_entrega = db.Column(db.Date)
    entregue_por = db.Column(db.String(120))

    # status da operação
    status = db.Column(db.String(20), default='entregue')  # entregue / devolvido / descartado

    observacao = db.Column(db.String(255))
    data_devolucao = db.Column(db.DateTime)
    data_descarte = db.Column(db.DateTime)


# ============================
# HISTÓRICO DE MOVIMENTAÇÃO
# ============================
class HistoricoEpi(db.Model):
    __tablename__ = 'historico_epi'

    id = db.Column(db.Integer, primary_key=True)

    epi_id = db.Column(db.Integer, db.ForeignKey('epi.id'))
    data = db.Column(db.DateTime, default=datetime.utcnow)

    acao = db.Column(db.String(50))  # Cadastro / Ajuste / Entrega / Exclusão
    quantidade = db.Column(db.Integer)
    usuario = db.Column(db.String(120))  # quem fez a ação


# ============================
# LOG DO SISTEMA
# ============================
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(120))
    acao = db.Column(db.String(255))
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)


# ============================
# LOGIN MANAGER
# ============================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



# ============================
# MIGRAÇÃO AUTOMÁTICA SQLITE
# ============================
def _sqlite_path_from_uri():
    uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if uri.startswith("sqlite:///"):
        return uri.replace("sqlite:///", "")
    if uri.startswith("sqlite:////"):  # caminho absoluto
        return uri.replace("sqlite:////", "/")
    return ""


def _ensure_table_columns():
    """
    Garante as colunas novas no SQLite sem precisar recriar nada.
    - EntregaEpi.status (TEXT DEFAULT 'entregue')
    - EntregaEpi.observacao (TEXT NULL)
    - EntregaEpi.data_devolucao (TEXT NULL)
    - EntregaEpi.data_descarte (TEXT NULL)
    - Epi.quantidade (INTEGER DEFAULT 0)
    - Epi.codigo_produto (TEXT NULL)
    - Epi.observacao (TEXT NULL)
    """
    db_path = _sqlite_path_from_uri()
    if not db_path or not os.path.exists(db_path):
        return

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        # --- EntregaEpi ---
        cur.execute("PRAGMA table_info(EntregaEpi);")
        entrega_cols = [r[1] for r in cur.fetchall()]

        if "status" not in entrega_cols:
            cur.execute("ALTER TABLE EntregaEpi ADD COLUMN status TEXT DEFAULT 'entregue'")
        if "observacao" not in entrega_cols:
            cur.execute("ALTER TABLE EntregaEpi ADD COLUMN observacao TEXT")
        if "data_devolucao" not in entrega_cols:
            cur.execute("ALTER TABLE EntregaEpi ADD COLUMN data_devolucao TEXT")
        if "data_descarte" not in entrega_cols:
            cur.execute("ALTER TABLE EntregaEpi ADD COLUMN data_descarte TEXT")

        # --- Epi ---
        cur.execute("PRAGMA table_info(Epi);")
        epi_cols = [r[1] for r in cur.fetchall()]

        if "quantidade" not in epi_cols:
            cur.execute("ALTER TABLE Epi ADD COLUMN quantidade INTEGER DEFAULT 0")
        if "codigo_produto" not in epi_cols:
            cur.execute("ALTER TABLE Epi ADD COLUMN codigo_produto TEXT")
        if "observacao" not in epi_cols:
            cur.execute("ALTER TABLE Epi ADD COLUMN observacao TEXT")

        con.commit()
        con.close()
    except Exception as e:
        print(f"[WARN] Migração automática SQLite falhou: {e}")


# ============================
# FUNÇÃO PARA REGISTRAR LOGS
# ============================
def registrar_log(usuario, acao):
    novo_log = Log(usuario=usuario, acao=acao, data_hora=datetime.now())
    db.session.add(novo_log)
    db.session.commit()


# ============================
# ROTA INICIAL
# ============================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# ============================
# ROTAS PRINCIPAIS
# ============================
@app.route('/login', methods=['GET', 'POST'])
def login():
    erro_login = None  # variável local, exclusiva da tela de login

    if request.method == 'POST':
        login_usuario = (request.form.get('login') or '').strip()
        senha = request.form.get('senha') or ''
        user = User.query.filter_by(login=login_usuario, senha=senha).first()

        if user:
            login_user(user)
            registrar_log(user.nome, "Realizou login no sistema")
            return redirect(url_for('dashboard'))
        else:
            erro_login = "⚠️ Login ou senha incorretos!"

    return render_template('login.html', erro_login=erro_login)


@app.route('/logout')
@login_required
def logout():
    registrar_log(current_user.nome, "Saiu do sistema")
    logout_user()
    return redirect(url_for('login'))


# ============================
# DASHBOARD
# ============================
@app.route('/dashboard')
@login_required
def dashboard():
    # ---------------------------
    # RECEBENDO FILTROS (opcional)
    # ---------------------------
    data_inicio_str = request.args.get('data_inicio', '').strip()
    data_fim_str = request.args.get('data_fim', '').strip()

    filtro_ativo = False
    dt_inicio = None
    dt_fim = None

    # tenta interpretar as datas em dois formatos
    def parse_data(s):
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    if data_inicio_str and data_fim_str:
        dt_inicio = parse_data(data_inicio_str)
        dt_fim = parse_data(data_fim_str)
        if dt_inicio and dt_fim:
            # fim do dia
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
            filtro_ativo = True

    # ---------------------------
    # MÉTRICAS FIXAS (SEM FILTRO)
    # ---------------------------
    total_epis = Epi.query.count()
    total_funcionarios = Funcionario.query.count()
    total_usuarios = User.query.count()

    # ---------------------------
    # ESTOQUE CRÍTICO
    # ---------------------------
    epis_criticos = Epi.query.filter(Epi.quantidade <= 10).all()
    total_criticos = len(epis_criticos)
    nomes_criticos = [e.nome for e in epis_criticos]
    qtd_criticos = [e.quantidade for e in epis_criticos]

    # ---------------------------
    # EPIs VENCIDOS
    # ---------------------------
    hoje = date.today()
    vencidos = []
    for e in Epi.query.all():
        try:
            validade = datetime.strptime(e.validade_ca, "%d/%m/%Y").date()
            if validade < hoje:
                vencidos.append(e)
        except Exception:
            pass
    total_vencidos = len(vencidos)

    # ---------------------------
    # ENTREGAS NO MÊS (NÃO USA FILTRO)
    # ---------------------------
    inicio_mes = datetime(hoje.year, hoje.month, 1)
    entregas_mes = EntregaEpi.query.filter(
        EntregaEpi.data_entrega >= inicio_mes,
        EntregaEpi.status == 'entregue'
    ).count()

    # ==================================================================
    # ===============    CONSULTAS QUE USAM DATA    ====================
    # ==================================================================

    # BASE: entregas com status='entregue'
    base_entregas = EntregaEpi.query.filter(EntregaEpi.status == 'entregue')
    if filtro_ativo:
        base_entregas = base_entregas.filter(
            EntregaEpi.data_entrega >= dt_inicio,
            EntregaEpi.data_entrega <= dt_fim
        )

    # TOTAL DE ENTREGAS (considerando filtro se ativo)
    total_entregas = base_entregas.count()

    # PENDÊNCIAS – aqui considerei status='entregue' e quantidade > 0
    pendencias = base_entregas.filter(EntregaEpi.quantidade > 0).count()

    # ---------------------------
    # GRÁFICO: EPIs por Tipo (NÃO USA FILTRO)
    # ---------------------------
    epis = Epi.query.all()
    tipos_epi = [e.nome for e in epis]
    qtd_epi = [e.quantidade for e in epis]

    # ---------------------------
    # GRÁFICO: ENTREGAS POR COLABORADOR (USA FILTRO)
    # ---------------------------
    from sqlalchemy import func

    colab_query = (
        db.session.query(Funcionario.nome, func.count(EntregaEpi.id))
        .join(EntregaEpi, EntregaEpi.funcionario_id == Funcionario.id)
        .filter(EntregaEpi.status == 'entregue')
    )

    if filtro_ativo:
        colab_query = colab_query.filter(
            EntregaEpi.data_entrega >= dt_inicio,
            EntregaEpi.data_entrega <= dt_fim
        )

    colab_query = colab_query.group_by(Funcionario.nome).order_by(func.count(EntregaEpi.id).desc())
    colab_rows = colab_query.all()

    nomes_colabs = [row[0] for row in colab_rows]
    qtd_entregas = [int(row[1]) for row in colab_rows]

    # ---------------------------
    # TOP 5 EPIs MAIS USADOS (USA FILTRO)
    # ---------------------------
    usados_query = (
        db.session.query(Epi.nome, func.sum(EntregaEpi.quantidade))
        .join(EntregaEpi, EntregaEpi.epi_id == Epi.id)
        .filter(EntregaEpi.status == 'entregue')
    )

    if filtro_ativo:
        usados_query = usados_query.filter(
            EntregaEpi.data_entrega >= dt_inicio,
            EntregaEpi.data_entrega <= dt_fim
        )

    usados_query = usados_query.group_by(Epi.nome).order_by(func.sum(EntregaEpi.quantidade).desc()).limit(5)
    usados_rows = usados_query.all()

    nomes_epi_mais_usados = [row[0] for row in usados_rows]
    qtd_epi_mais_usados = [int(row[1] or 0) for row in usados_rows]

    # ---------------------------
    # RENDER
    # ---------------------------
    return render_template(
        'dashboard.html',
        user=current_user,

        # Cards principais
        total_epis=total_epis,
        total_entregas=total_entregas,
        total_funcionarios=total_funcionarios,
        total_usuarios=total_usuarios,

        # Cards avançados
        total_criticos=total_criticos,
        total_vencidos=total_vencidos,
        entregas_mes=entregas_mes,
        pendencias=pendencias,

        # Gráficos
        tipos_epi=tipos_epi,
        qtd_epi=qtd_epi,
        nomes_colabs=nomes_colabs,
        qtd_entregas=qtd_entregas,
        nomes_criticos=nomes_criticos,
        qtd_criticos=qtd_criticos,
        nomes_epi_mais_usados=nomes_epi_mais_usados,
        qtd_epi_mais_usados=qtd_epi_mais_usados
    )






# =====================================================
# FUNÇÃO PARA REGISTRAR HISTÓRICO
# =====================================================
def registrar_historico(epi_id, acao, quantidade, usuario):
    registro = HistoricoEpi(
        epi_id=epi_id,
        acao=acao,
        quantidade=quantidade,
        usuario=usuario
    )
    db.session.add(registro)
    db.session.commit()


# ============================
# EPIS
# ============================
@app.route('/epis', methods=['GET', 'POST'])
@login_required
def epis():
    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        codigo_produto = (request.form.get('codigo_produto') or '').strip()
        numero_ca = (request.form.get('numero_ca') or '').strip()
        validade_ca = (request.form.get('validade_ca') or '').strip()
        quantidade = int(request.form.get('quantidade') or 0)
        observacao = (request.form.get('observacao') or '').strip()

        if not nome or not validade_ca or quantidade < 0:
            flash('⚠️ Preencha corretamente os campos do EPI.')
            return redirect(url_for('epis'))

        novo_epi = Epi(
            nome=nome,
            codigo_produto=codigo_produto,
            numero_ca=numero_ca,
            validade_ca=validade_ca,
            quantidade=quantidade,
            observacao=observacao
        )

        db.session.add(novo_epi)
        db.session.commit()

        # 🔥 registra histórico
        registrar_historico(
            epi_id=novo_epi.id,
            acao="Cadastro",
            quantidade=quantidade,
            usuario=current_user.nome
        )

        registrar_log(current_user.nome, f"Cadastrou novo EPI: {nome}")
        flash('✅ EPI cadastrado com sucesso!')
        return redirect(url_for('epis'))

    # GET
    filtro = request.args.get('filtro', '').strip()
    epis_list = Epi.query.filter(Epi.nome.ilike(f"%{filtro}%")).all() if filtro else Epi.query.all()
    funcionarios = Funcionario.query.order_by(Funcionario.nome).all()

    return render_template(
        'epis.html',
        user=current_user,
        epis=epis_list,
        funcionarios=funcionarios,
        filtro=filtro
    )


# ============================
# EDITAR EPI
# ============================
@app.route('/editar_epi/<int:id>', methods=['POST'])
@login_required
def editar_epi(id):
    epi = Epi.query.get_or_404(id)

    quantidade_antiga = epi.quantidade

    epi.nome = (request.form.get('nome') or epi.nome).strip()
    epi.codigo_produto = (request.form.get('codigo_produto') or epi.codigo_produto).strip()
    epi.numero_ca = (request.form.get('numero_ca') or epi.numero_ca).strip()
    epi.validade_ca = (request.form.get('validade_ca') or epi.validade_ca).strip()
    epi.quantidade = int(request.form.get('quantidade') or epi.quantidade)
    epi.observacao = (request.form.get('observacao') or epi.observacao)

    db.session.commit()

    # 🔥 registra histórico apenas se a quantidade mudou
    if epi.quantidade != quantidade_antiga:
        ajuste = epi.quantidade - quantidade_antiga
        registrar_historico(
            epi_id=epi.id,
            acao="Ajuste de Estoque",
            quantidade=ajuste,
            usuario=current_user.nome
        )

    registrar_log(current_user.nome, f"Editou EPI: {epi.nome}")
    flash('✅ EPI atualizado com sucesso!')
    return redirect(url_for('epis'))


# ============================
# DELETAR EPI
# ============================
@app.route('/deletar_epi/<int:id>')
@login_required
def deletar_epi(id):
    epi = Epi.query.get_or_404(id)

    # 🔥 registra histórico ANTES de excluir
    registrar_historico(
        epi_id=epi.id,
        acao="Exclusão",
        quantidade=0,
        usuario=current_user.nome
    )

    registrar_log(current_user.nome, f"Excluiu EPI: {epi.nome}")

    db.session.delete(epi)
    db.session.commit()

    flash('🗑️ EPI removido com sucesso!')
    return redirect(url_for('epis'))


# ============================
# ENTREGA DE EPI
# ============================
@app.route('/entregar_epi', methods=['GET', 'POST'])
@login_required
def entregar_epi():
    if request.method == 'GET':
        return redirect(url_for('epis'))

    try:
        funcionario_id = int(request.form.get('funcionario_id') or 0)
        epi_id = int(request.form.get('epi_id') or 0)
        quantidade = int(request.form.get('quantidade') or 0)
        validade_str = request.form.get('validade_entrega')
        senha = request.form.get('senha_validacao') or ''
        observacao = (request.form.get('observacao') or '').strip()

        funcionario = Funcionario.query.get(funcionario_id)
        epi = Epi.query.get(epi_id)

        if not funcionario or not epi:
            flash('⚠️ Funcionário ou EPI inválido!')
            return redirect(url_for('epis'))

        if (funcionario.senha_validacao or '') != senha:
            flash('🚫 Senha de validação incorreta!')
            return redirect(url_for('epis'))

        if quantidade <= 0:
            flash('⚠️ Informe uma quantidade válida.')
            return redirect(url_for('epis'))

        if epi.quantidade < quantidade:
            flash('⚠️ Estoque insuficiente!')
            return redirect(url_for('epis'))

        validade_data = datetime.strptime(validade_str, "%Y-%m-%d").date() if validade_str else None

        nova_entrega = EntregaEpi(
            funcionario_id=funcionario.id,
            epi_id=epi.id,
            quantidade=quantidade,
            entregue_por=current_user.nome,
            validade_entrega=validade_data,
            status='entregue',
            observacao=observacao or None
        )

        # diminui quantidade
        epi.quantidade = max(epi.quantidade - quantidade, 0)

        db.session.add(nova_entrega)
        db.session.commit()

        # 🔥 histórico da entrega
        registrar_historico(
            epi_id=epi.id,
            acao="Entrega",
            quantidade=quantidade,
            usuario=current_user.nome
        )

        registrar_log(
            current_user.nome,
            f"Entregou {quantidade}x {epi.nome} a {funcionario.nome}"
        )

        flash(f'✅ {quantidade}x {epi.nome} entregue a {funcionario.nome}.')
        return redirect(url_for('epis'))

    except Exception as e:
        db.session.rollback()
        flash(f'🚫 Erro ao registrar entrega: {str(e)}')
        return redirect(url_for('epis'))


# ============================
# FICHA DE EPI (PDF)
# ============================
@app.route('/ficha_epi/<int:funcionario_id>')
@login_required
def ficha_epi(funcionario_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from datetime import datetime
    from io import BytesIO
    import os


    # -----------------------------
    # BUSCA DO COLABORADOR
    # -----------------------------
    func = Funcionario.query.get_or_404(funcionario_id)

    # -----------------------------
    # FILTRO DE PERÍODO
    # -----------------------------
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

    query = EntregaEpi.query.filter_by(funcionario_id=funcionario_id)

    if data_inicio and data_fim:
        try:
            dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)

            query = query.filter(
                EntregaEpi.data_entrega >= dt_inicio,
                EntregaEpi.data_entrega <= dt_fim
            )
        except Exception as e:
            print("Erro no filtro:", e)

    entregas = query.order_by(EntregaEpi.data_entrega.asc()).all()

    # -----------------------------
    # INÍCIO DO PDF
    # -----------------------------
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ===== MOLDURA =====
    pdf.setStrokeColorRGB(0.6, 0.6, 0.6)
    pdf.setLineWidth(0.5)
    pdf.rect(20, 20, width - 40, height - 40)

    # ===== LOGO =====
    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        pdf.drawImage(logo_path, 30, height - 80, width=60, height=40, mask='auto')

    # ===== CABEÇALHO =====
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, height - 50, "EMPRESA")
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(width / 2, height - 63,
        "CNPJ: 00.000.000/0001-00  •  Endereço: Av. Principal, 123 – Japeri/RJ  •  Tel: (21) 97123-5331")
    pdf.drawCentredString(width / 2, height - 75,
        "Responsável Técnico: Jonatas de Alvarenga Galdino")

    # ===== TÍTULO =====
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, height - 110, "FICHA DE CONTROLE DE EPI")
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(width / 2, height - 122,
        "Registro de entrega, uso e devolução de Equipamentos de Proteção Individual")

    # ===== DADOS DO COLABORADOR =====
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, height - 150, "DADOS DO COLABORADOR")
    pdf.line(40, height - 152, width - 40, height - 152)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, height - 165, f"Nome: {func.nome}")
    pdf.drawRightString(width - 40, height - 165,
        f"Data de emissão: {datetime.now().strftime('%d/%m/%Y')}")
    pdf.drawString(40, height - 177, f"Matrícula: {func.matricula}")
    pdf.drawString(40, height - 189, f"Setor: {func.setor or '-'}")

    # ===== PERÍODO =====
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, height - 205, "PERÍODO DO RELATÓRIO")
    pdf.line(40, height - 207, width - 40, height - 207)

    pdf.setFont("Helvetica", 9)
    if data_inicio and data_fim:
        pdf.drawString(40, height - 220,
                       f"Movimentações entre: {dt_inicio.strftime('%d/%m/%Y')} até {dt_fim.strftime('%d/%m/%Y')}")
    else:
        pdf.drawString(40, height - 220, "Movimentações de todo o período")

    # ===== TERMO =====
    termo_texto = (
        "Declaro para os devidos fins que recebi os EPI's (Equipamentos de Proteção Individual) abaixo descritos "
        "e me comprometo a:<br/><br/>"
        "• Usá-los apenas para as finalidades a que se destinam;<br/>"
        "• Responsabilizar-me por sua guarda e conservação;<br/>"
        "• Comunicar ao empregador qualquer modificação que os torne impróprios para o uso;<br/>"
        "• Responsabilizar-me pela danificação do E.P.I. devido ao uso inadequado ou fora das atividades a que se destinam, "
        "bem como pelo seu extravio.<br/><br/>"
        "Declaro ainda estar ciente de que o uso é obrigatório, sob pena de ser punido conforme LEI nº 6.514, "
        "de 22/12/1977, artigo 158:<br/>"
        "“Recusa injustificada ao uso do EPI constitui ato faltoso, autorizando a dispensa por justa causa.”<br/><br/>"
        "Declaro também que recebi treinamento referente ao uso e conservação do E.P.I. segundo as Normas "
        "de Segurança do Trabalho."
    )

    estilo_termo = ParagraphStyle(
        name="termo",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=0
    )

    p = Paragraph(termo_texto, estilo_termo)

    termo_width, termo_height = p.wrap(width - 80, 500)

    termo_y = height - 260
    p.drawOn(pdf, 40, termo_y - termo_height)

    # Atualiza o Y abaixo do termo automaticamente
    y_after_termo = termo_y - termo_height - 20

    # ===== TABELA =====
    data = [["Descrição do EPI", "CA", "Qtde", "Entrega", "Devolução/Descarte", "Status"]]

    for e in entregas:
        data_entrega = e.data_entrega.strftime('%d/%m/%Y')

        if e.data_devolucao:
            data_dev = e.data_devolucao.strftime('%d/%m/%Y')
        elif e.data_descarte:
            data_dev = e.data_descarte.strftime('%d/%m/%Y')
        else:
            data_dev = "-"

        data.append([
            e.epi.nome,
            e.epi.numero_ca or "-",
            str(e.quantidade),
            data_entrega,
            data_dev,
            e.status.capitalize()
        ])

    table = Table(data, colWidths=[150, 50, 40, 80, 90, 60])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
    ]))

    table_width, table_height = table.wrapOn(pdf, width, height)

    table_y = y_after_termo - table_height
    table.drawOn(pdf, 40, table_y)

    # ===== ASSINATURAS =====
    y_ass = table_y - 60
    pdf.setLineWidth(0.4)

    pdf.line(100, y_ass, width - 100, y_ass)
    pdf.drawCentredString(width / 2, y_ass - 12, "Assinatura do Colaborador")

    pdf.line(100, y_ass - 50, width - 100, y_ass - 50)
    pdf.drawCentredString(width / 2, y_ass - 62, "Assinatura do Responsável Técnico")

    # ===== RODAPÉ =====
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.drawCentredString(width / 2, 35,
        "Documento gerado automaticamente pelo Sistema de Controle de EPI – AdaptLink")

    pdf.showPage()
    pdf.save()

    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'inline; filename=ficha_{func.nome.replace(' ', '_')}.pdf'
    )

    return response




# ============================
# ENTREGAS / DEVOLUÇÕES / DESCARTES
# ============================
@app.route('/entregas')
@login_required
def entregas():
    """Tela principal: mostra apenas entregas ativas (status='entregue').
       Modal de relatórios recebe histórico completo.
    """

    colaborador = request.args.get('colaborador', '').strip()
    epi_nome = request.args.get('epi', '').strip()

    data_inicio = request.args.get('data_inicio', '')
    data_fim = request.args.get('data_fim', '')

    # --------------------------------------------
    # 🔵 TABELA PRINCIPAL: SOMENTE ENTREGAS ATIVAS
    # --------------------------------------------
    query = (EntregaEpi.query
             .join(Funcionario)
             .join(Epi)
             .filter(EntregaEpi.status == 'entregue'))

    if colaborador:
        query = query.filter(Funcionario.nome.ilike(f"%{colaborador}%"))

    if epi_nome:
        query = query.filter(Epi.nome.ilike(f"%{epi_nome}%"))

    if data_inicio and data_fim:
        try:
            dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)

            query = query.filter(
                EntregaEpi.data_entrega >= dt_inicio,
                EntregaEpi.data_entrega <= dt_fim
            )
        except:
            pass

    entregas_list = query.order_by(EntregaEpi.data_entrega.desc()).all()

    # --------------------------------------------
    # 📘 HISTÓRICO COMPLETO (entregue/devolvido/descartado)
    # --------------------------------------------
    historico = (EntregaEpi.query
                 .order_by(EntregaEpi.data_entrega.desc())
                 .all())

    return render_template(
        'entregas.html',
        user=current_user,
        entregas=entregas_list,
        historico=historico
    )


# =====================================================
# 🔵 DEVOLUÇÃO PARCIAL / TOTAL (CORRIGIDO)
# =====================================================
@app.route("/devolver_epi/<int:entrega_id>", methods=["POST"])
@login_required
def devolver_epi(entrega_id):
    data = request.get_json()
    qtd = int(data.get("quantidade", 0))

    entrega = EntregaEpi.query.get_or_404(entrega_id)
    epi = entrega.epi

    if entrega.status in ("devolvido", "descartado"):
        return jsonify({"status": "erro", "mensagem": "Esta entrega já foi finalizada."}), 400

    if qtd <= 0 or qtd > entrega.quantidade:
        return jsonify({"status": "erro", "mensagem": "Quantidade inválida."}), 400

    # 🔵 DEVOLUÇÃO TOTAL
    if qtd == entrega.quantidade:
        entrega.status = "devolvido"
        entrega.data_devolucao = datetime.utcnow()

    # 🔵 DEVOLUÇÃO PARCIAL → mantém quantidade REAL devolvida
    entrega.quantidade = qtd   # ← AGORA NÃO ZERA MAIS
    epi.quantidade += qtd      # ← Volta para o estoque

    db.session.commit()

    return jsonify({"status": "ok"}), 200



# =====================================================
# 🔴 DESCARTE PARCIAL / TOTAL (CORRIGIDO)
# =====================================================
@app.route("/descartar_epi/<int:entrega_id>", methods=["POST"])
@login_required
def descartar_epi(entrega_id):
    data = request.get_json()
    qtd = int(data.get("quantidade", 0))

    entrega = EntregaEpi.query.get_or_404(entrega_id)
    epi = entrega.epi

    if entrega.status in ("devolvido", "descartado"):
        return jsonify({"status": "erro", "mensagem": "Esta entrega já foi finalizada."}), 400

    if qtd <= 0 or qtd > entrega.quantidade:
        return jsonify({"status": "erro", "mensagem": "Quantidade inválida."}), 400

    # 🔴 DESCARTE TOTAL
    if qtd == entrega.quantidade:
        entrega.status = "descartado"
        entrega.data_descarte = datetime.utcnow()

    # 🔴 DESCARTE PARCIAL → mantém quantidade REAL descartada
    entrega.quantidade = qtd   # ← NÃO ZERA MAIS
    # ❗ Não volta para o estoque
    # epi.quantidade NÃO É ALTERADO

    db.session.commit()

    return jsonify({"status": "ok"}), 200


# =========================================
# GERAR PDF DE MOVIMENTAÇÃO — ESTILO FICHA + TERMO (FINAL)
# =========================================
@app.route('/pdf_movimentacao/<int:entrega_id>')
@login_required
def pdf_movimentacao(entrega_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors
    import os

    entrega = EntregaEpi.query.get_or_404(entrega_id)
    func = entrega.funcionario
    epi = entrega.epi

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ======================= MOLDURA =======================
    pdf.setStrokeColorRGB(0.6, 0.6, 0.6)
    pdf.setLineWidth(0.5)
    pdf.rect(20, 20, width - 40, height - 40)

    # ======================= LOGO =======================
    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        pdf.drawImage(logo_path, 30, height - 80, width=60, height=40, mask='auto')

    # ======================= CABEÇALHO =======================
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, height - 50, "EMPRESA")

    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(
        width / 2, height - 63,
        "CNPJ: 00.000.000/0001-00  •  Endereço: Av. Principal, 123 – Japeri/RJ  •  Tel: (21) 97123-5331"
    )
    pdf.drawCentredString(
        width / 2, height - 75,
        "Responsável Técnico: Jonatas de Alvarenga Galdino"
    )

    # ======================= TÍTULO =======================
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, height - 110, "MOVIMENTAÇÃO DE EPI")

    # ======================= DADOS DO COLABORADOR =======================
    y = height - 150
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "DADOS DO COLABORADOR")
    pdf.line(40, y - 2, width - 40, y - 2)

    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, y - 15, f"Nome: {func.nome}")
    pdf.drawRightString(width - 40, y - 15, f"Data de emissão: {datetime.now().strftime('%d/%m/%Y')}")
    pdf.drawString(40, y - 27, f"Matrícula: {func.matricula}")
    pdf.drawString(40, y - 39, f"Setor: {func.setor or '-'}")

    # ======================= TERMO DE RESPONSABILIDADE =======================
    y_termo = y - 70

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y_termo, "TERMO DE RESPONSABILIDADE")
    pdf.line(40, y_termo - 2, width - 40, y_termo - 2)

    termo = (
        "Declaro para os devidos fins que recebi o(s) EPI(s) relacionado(s) neste documento e me comprometo a:\n"
        "• Usá-los apenas para as finalidades a que se destinam;\n"
        "• Responsabilizar-me por sua guarda e conservação;\n"
        "• Comunicar ao empregador qualquer modificação que os torne impróprios para o uso;\n"
        "• Responsabilizar-me pela danificação do E.P.I. devido ao uso inadequado ou fora das atividades a que se destinam, bem como pelo seu extravio.\n\n"
        "Declaro ainda estar ciente de que o uso é obrigatório, sob pena de ser punido conforme LEI nº 6.514/1977, artigo 158:\n"
        "“Recusa injustificada ao uso do EPI constitui ato faltoso, autorizando a dispensa por justa causa.”\n\n"
        "Declaro também que recebi treinamento referente ao uso e conservação do E.P.I. segundo as Normas de Segurança do Trabalho."
    )

    txt = pdf.beginText(40, y_termo - 20)
    txt.setFont("Helvetica", 8.5)
    txt.setLeading(12)

    for linha in termo.split("\n"):
        txt.textLine(linha.strip())

    pdf.drawText(txt)

    # Posição final após o texto
    y_after_termo = txt.getY() - 25

    # ======================= TABELA — DETALHES DA MOVIMENTAÇÃO =======================
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y_after_termo, "DETALHES DA MOVIMENTAÇÃO")
    pdf.line(40, y_after_termo - 2, width - 40, y_after_termo - 2)

    tabela_dados = [
        ["Campo", "Informação"],
        ["EPI", epi.nome],
        ["CA", epi.numero_ca or "-"],
        ["Quantidade", str(entrega.quantidade)],
        ["Status", entrega.status.capitalize()],
        ["Entregue por", entrega.entregue_por or "-"],
        ["Data da operação", entrega.data_entrega.strftime("%d/%m/%Y %H:%M")]
    ]

    if entrega.status == "devolvido" and entrega.data_devolucao:
        tabela_dados.append(["Data da devolução", entrega.data_devolucao.strftime("%d/%m/%Y %H:%M")])

    if entrega.status == "descartado" and entrega.data_descarte:
        tabela_dados.append(["Data do descarte", entrega.data_descarte.strftime("%d/%m/%Y %H:%M")])

    table = Table(tabela_dados, colWidths=[160, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Posição com espaçamento para não encostar no texto acima
    table_y = y_after_termo - 40 - (len(tabela_dados) * 18)

    table.wrapOn(pdf, width, height)
    table.drawOn(pdf, 40, table_y)

    # ======================= ASSINATURAS =======================
    y_assin = 120
    pdf.setFont("Helvetica", 9)

    pdf.line(100, y_assin, width - 100, y_assin)
    pdf.drawCentredString(width / 2, y_assin - 10, "Assinatura do Colaborador")

    pdf.line(100, y_assin - 50, width - 100, y_assin - 50)
    pdf.drawCentredString(width / 2, y_assin - 60, "Assinatura do Responsável Técnico")

    # ======================= RODAPÉ =======================
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.drawCentredString(
        width / 2, 35,
        "Documento gerado automaticamente pelo Sistema de Controle de EPI – AdaptLink"
    )

    pdf.showPage()
    pdf.save()

    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=movimentacao_{entrega_id}.pdf'
    return response

# ============================
# FUNCIONÁRIOS / LOGS / USUÁRIOS
# ============================
@app.route('/cadastro_funcionarios', methods=['GET', 'POST'])
@login_required
def cadastro_funcionarios():
    if current_user.role not in ['admin', 'supervisor']:
        flash('🚫 Acesso restrito.')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        matricula = (request.form.get('matricula') or '').strip()
        setor = (request.form.get('setor') or '').strip()
        data_admissao = request.form.get('data_admissao')

        if not nome or not matricula or not setor or not data_admissao:
            flash('⚠️ Preencha todos os campos obrigatórios!')
            return redirect(url_for('cadastro_funcionarios'))

        novo_func = Funcionario(
            nome=nome,
            matricula=matricula,
            setor=setor,
            data_admissao=datetime.strptime(data_admissao, "%Y-%m-%d").date()
        )
        db.session.add(novo_func)
        db.session.commit()
        registrar_log(current_user.nome, f"Cadastrou funcionário: {nome}")
        flash('✅ Funcionário cadastrado com sucesso!')
        return redirect(url_for('cadastro_funcionarios'))

    funcionarios = Funcionario.query.order_by(Funcionario.nome).all()
    return render_template('cadastro_colaboradores.html', user=current_user, funcionarios=funcionarios)

# ============================
# EDITAR FUNCIONÁRIO
# ============================
@app.route('/editar_funcionario/<int:id>', methods=['POST'])
@login_required
def editar_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)

    funcionario.nome = request.form.get('nome') or funcionario.nome
    funcionario.matricula = request.form.get('matricula') or funcionario.matricula
    funcionario.setor = request.form.get('setor') or funcionario.setor
    funcionario.data_admissao = request.form.get('data_admissao') or funcionario.data_admissao

    db.session.commit()

    flash("✅ Funcionário atualizado com sucesso!", "success")
    return redirect(url_for('cadastro_funcionarios'))



@app.route('/definir_senha_funcionario/<int:id>', methods=['POST'])
@login_required
def definir_senha_funcionario(id):
    func = Funcionario.query.get_or_404(id)
    func.senha_validacao = request.form.get('senha_validacao') or ''
    db.session.commit()
    registrar_log(current_user.nome, f"Definiu senha de validação para {func.nome}")
    flash('🔒 Senha de validação cadastrada com sucesso!')
    return redirect(url_for('cadastro_funcionarios'))


@app.route('/deletar_funcionario/<int:id>')
@login_required
def deletar_funcionario(id):
    func = Funcionario.query.get_or_404(id)
    EntregaEpi.query.filter_by(funcionario_id=id).delete()
    db.session.delete(func)
    db.session.commit()
    registrar_log(current_user.nome, f"Excluiu funcionário: {func.nome}")
    flash('🗑️ Funcionário e entregas associadas removidos com sucesso!')
    return redirect(url_for('cadastro_funcionarios'))


# ============================
# LOGS
# ============================
@app.route('/logs')
@login_required
def logs():
    if current_user.role not in ['admin', 'supervisor']:
        flash('🚫 Acesso restrito.')
        return redirect(url_for('dashboard'))

    # --------- Filtros recebidos ---------
    busca = request.args.get('busca', '').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()

    # Query base
    query = Log.query

    # --------- Filtro por texto ---------
    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            db.or_(
                Log.usuario.ilike(termo),
                Log.acao.ilike(termo)
            )
        )

    # --------- Filtro por período ---------
    if data_inicio and data_fim:
        try:
            dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")

            # Ajusta fim do dia para 23:59:59
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)

            query = query.filter(
                Log.data_hora.between(dt_inicio, dt_fim)
            )
        except Exception as e:
            print("Erro no filtro de data:", e)

    # Ordenação
    logs_filtrados = query.order_by(Log.data_hora.desc()).all()

    return render_template('logs.html',
                           user=current_user,
                           logs=logs_filtrados)


# ============================
# USUÁRIOS
# ============================
@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
def usuarios():
    if current_user.role != 'admin':
        flash('🚫 Acesso restrito a administradores.')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = (request.form.get('nome') or '').strip()
        login_usuario = (request.form.get('login') or '').strip()
        senha = request.form.get('senha') or ''
        role = request.form.get('role') or 'user'

        if not nome or not login_usuario or not senha:
            flash('⚠️ Preencha todos os campos!')
            return redirect(url_for('usuarios'))

        if User.query.filter_by(login=login_usuario).first():
            flash('⚠️ Já existe um usuário com este login.')
            return redirect(url_for('usuarios'))

        novo_usuario = User(nome=nome, login=login_usuario, senha=senha, role=role)
        db.session.add(novo_usuario)
        db.session.commit()
        registrar_log(current_user.nome, f"Cadastrou usuário: {nome}")
        flash('✅ Usuário cadastrado com sucesso!')
        return redirect(url_for('usuarios'))

    usuarios_list = User.query.all()
    return render_template('usuarios.html', user=current_user, usuarios=usuarios_list)


@app.route('/editar_usuario/<int:id>', methods=['POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'admin':
        flash('🚫 Acesso restrito.')
        return redirect(url_for('dashboard'))

    usuario = User.query.get_or_404(id)
    usuario.login = (request.form.get('login') or usuario.login).strip()
    usuario.role = request.form.get('role') or usuario.role
    db.session.commit()
    registrar_log(current_user.nome, f"Editou usuário: {usuario.nome}")
    flash('✅ Usuário atualizado com sucesso!')
    return redirect(url_for('usuarios'))


@app.route('/deletar_usuario/<int:id>')
@login_required
def deletar_usuario(id):
    if current_user.role != 'admin':
        flash('🚫 Acesso restrito.')
        return redirect(url_for('dashboard'))

    usuario = User.query.get_or_404(id)
    if usuario.login == 'admin':
        flash('🚫 Não é possível excluir o usuário administrador padrão.')
        return redirect(url_for('usuarios'))

    db.session.delete(usuario)
    db.session.commit()
    registrar_log(current_user.nome, f"Excluiu usuário: {usuario.nome}")
    flash('🗑️ Usuário excluído com sucesso!')
    return redirect(url_for('usuarios'))


# ============================
# CRIAÇÃO DO ADMIN PADRÃO
# ============================
def criar_admin_padrao():
    if User.query.count() == 0:
        admin = User(nome="Administrador", login="admin", senha="1234", role="admin")
        db.session.add(admin)
        db.session.commit()
        print("✅ Usuário admin criado (login: admin / senha: 1234)")


# ============================
# EXECUÇÃO
# ============================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        _ensure_table_columns()   # migração automática das novas colunas
        criar_admin_padrao()
    app.run(debug=True)
