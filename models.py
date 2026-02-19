from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ImportacaoLote(db.Model):
    __tablename__ = 'importacao_lotes'
    id = db.Column(db.Integer, primary_key=True)
    data_importacao = db.Column(db.DateTime, default=datetime.utcnow)
    periodo_referencia = db.Column(db.String(50))
    total_itens = db.Column(db.Integer)
    total_alterados = db.Column(db.Integer)
    
    # Relacionamento para ver as mudanças deste lote específico
    mudancas = db.relationship('HistoricoMudanca', backref='lote', lazy=True)

class HistoricoMudanca(db.Model):
    __tablename__ = 'historico_mudancas'
    id = db.Column(db.Integer, primary_key=True)
    lote_id = db.Column(db.Integer, db.ForeignKey('importacao_lotes.id'), nullable=False)
    pedido = db.Column(db.String(50))
    codigo_barras = db.Column(db.String(50))
    status_anterior = db.Column(db.String(50))
    status_novo = db.Column(db.String(50))
    item_desc = db.Column(db.String(255))
    data_mudanca = db.Column(db.DateTime, default=datetime.utcnow)

class PedidoItens(db.Model):
    __tablename__ = 'pedido_itens'
    
    id = db.Column(db.Integer, primary_key=True)
    pedido = db.Column(db.String(50), nullable=False)
    colecao = db.Column(db.String(100))
    item_desc = db.Column(db.String(255))
    artigo = db.Column(db.String(100))
    tamanho = db.Column(db.String(20))
    codigo_barras = db.Column(db.String(50), nullable=False)
    embarque = db.Column(db.String(50))
    entrega = db.Column(db.String(50))
    nota_fiscal = db.Column(db.String(50))
    serie = db.Column(db.String(20))
    valor_liquido = db.Column(db.Float)
    valor_un = db.Column(db.Float)
    pecas = db.Column(db.Integer)
    status = db.Column(db.String(50))
    periodo_referencia = db.Column(db.String(50))
    ultima_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('pedido', 'codigo_barras', name='_pedido_item_uc'),
    )

    def __repr__(self):
        return f'<Pedido {self.pedido} - {self.artigo}>'