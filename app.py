import os
import sys
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, PedidoItens, ImportacaoLote, HistoricoMudanca
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timedelta
from sqlalchemy import func
import numpy as np

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hering_franchise_secret_key")
app.jinja_env.add_extension(\'jinja2.ext.do\')

# Configuração do Banco de Dados - PostgreSQL
# Usará a variável de ambiente DATABASE_URL fornecida pelo Render
app.config[\'SQLALCHEMY_DATABASE_URI\'] = os.environ.get(\'DATABASE_URL\')
app.config[\'SQLALCHEMY_TRACK_MODIFICATIONS\'] = False

db.init_app(app)

# Criar as tabelas se não existirem (apenas para desenvolvimento local, no Render o DB é provisionado)
with app.app_context():
    db.create_all()

def get_local_now():
    """Retorna o horário atual ajustado para o fuso de Brasília (UTC-3)"""
    return datetime.utcnow() - timedelta(hours=3)

@app.route(\'/\')
@app.route(\'/dashboard\')
def index():
    """Renderiza o Dashboard principal com indicadores consolidados."""
    try:
        total_itens = db.session.query(func.count(PedidoItens.id)).scalar() or 0
        
        # Contagem de Faturados/Entregues (Case Insensitive)
        faturados_count = db.session.query(func.count(PedidoItens.id)).filter(
            PedidoItens.status.ilike(\'faturado\') | PedidoItens.status.ilike(\'entregue\')
        ).scalar() or 0
        
        # Contagem de Cancelados
        cancelados_count = db.session.query(func.count(PedidoItens.id)).filter(
            PedidoItens.status.ilike(\'cancelado\')
        ).scalar() or 0
        
        # Volume Financeiro (ignorando cancelados)
        total_valor = db.session.query(func.sum(PedidoItens.valor_liquido)).filter(
            ~PedidoItens.status.ilike(\'cancelado\')
        ).scalar() or 0.0

        periodos_raw = db.session.query(PedidoItens.periodo_referencia).distinct().all()
        periodos = [p[0] for p in periodos_raw if p[0]]

        return render_template(\'index.html\', 
                               total_itens=total_itens,
                               faturados_count=faturados_count,
                               cancelados_count=cancelados_count,
                               total_valor=total_valor,
                               periodos=periodos)
    except Exception as e:
        print(f"Erro ao carregar dashboard: {e}")
        return render_template(\'index.html\', total_itens=0, faturados_count=0, cancelados_count=0, total_valor=0, periodos=[], erro=str(e))


@app.route(\'/importar\', methods=[\'GET\', \'POST\'])
def importar():
    if request.method == \'POST\':
        file = request.files.get(\'file\')
        periodo = request.form.get(\'periodo\')

        if not file or not periodo:
            flash("Selecione o arquivo Excel (.xlsx) e informe o período.", "error")
            return redirect(url_for(\'importar\'))

        try:
            # 1. Leitura de EXCEL (.xlsx)
            df = pd.read_excel(file, skiprows=7, engine=\'openpyxl\', dtype=str)

            # 2. Limpeza de colunas
            df.columns = [str(c).strip() for c in df.columns]
            
            # 3. Tratamento de valores vazios
            df = df.replace({np.nan: None})

            data_lote = get_local_now()
            novo_lote = ImportacaoLote(
                data_importacao=data_lote,
                periodo_referencia=periodo,
                total_itens=len(df),
                total_alterados=0
            )
            db.session.add(novo_lote)
            db.session.flush()

            mudancas_detectadas = 0
            itens_processados_keys = set()

            for _, row in df.iterrows():
                def clean_val(val):
                    if val is None: return None
                    s = str(val).strip()
                    if s.endswith(\'\.0\'): s = s[:-2]
                    return s if s.lower() not in [\'nan\', \'none\', \'\'] else None

                pedido_val = clean_val(row.get(\'Pedido\'))
                sku_val = clean_val(row.get(\'Código de barras\'))

                if not pedido_val or not sku_val:
                    continue

                item_key = f"{pedido_val}_{sku_val}"
                if item_key in itens_processados_keys:
                    continue
                
                try:
                    v_liq_raw = row.get(\'Valor Líquido\')
                    if v_liq_raw:
                        v_liq = float(str(v_liq_raw).replace(\'\', \'.\'))
                    else:
                        v_liq = 0.0
                except:
                    v_liq = 0.0

                try:
                    pecas_val = int(float(row.get(\'Peças\') or 0))
                except:
                    pecas_val = 0

                novo_status = str(row.get(\'Status\') or "Pendente").strip()
                nf_val = clean_val(row.get(\'Nota Fiscal\'))

                # 4. Verificação de Histórico (se o item já existe e o status mudou)
                item_db = PedidoItens.query.filter_by(pedido=pedido_val, codigo_barras=sku_val).first()
                if item_db:
                    status_antigo = (item_db.status or "").strip().upper()
                    if status_antigo != novo_status.upper():
                        mudanca = HistoricoMudanca(
                            lote_id=novo_lote.id,
                            pedido=pedido_val,
                            codigo_barras=sku_val,
                            status_anterior=item_db.status or "SEM STATUS",
                            status_novo=novo_status,
                            item_desc=item_db.item_desc or str(row.get(\'Item\') or \'S/D\'),
                            data_mudanca=data_lote
                        )
                        db.session.add(mudanca)
                        mudancas_detectadas += 1

                # 5. UPSERT (Grava ou Atualiza) - Usando insert do PostgreSQL
                db_values = {
                    \'pedido\': pedido_val,
                    \'codigo_barras\': sku_val,
                    \'item_desc\': str(row.get(\'Item\') or \'\'),
                    \'valor_liquido\': v_liq,
                    \'status\': novo_status,
                    \'periodo_referencia\': periodo,
                    \'ultima_atualizacao\': data_lote,
                    \'nota_fiscal\': nf_val,
                    \'colecao\': str(row.get(\'Coleção\') or \'\'),
                    \'tamanho\': str(row.get(\'Tamanho\') or \'\'),
                    \'artigo\': str(row.get(\'Artigo\') or \'\'),
                    \'embarque\': str(row.get(\'Embarque\') or \'\'),
                    \'entrega\': str(row.get(\'Entrega\') or \'\'),
                    \'pecas\': pecas_val
                }

                stmt = insert(PedidoItens).values(db_values)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=[\'pedido\', \'codigo_barras\'],
                    set_={
                        \'status\': db_values[\'status\'],
                        \'ultima_atualizacao\': db_values[\'ultima_atualizacao\'],
                        \'valor_liquido\': db_values[\'valor_liquido\'],
                        \'nota_fiscal\': db_values[\'nota_fiscal\'],
                        \'item_desc\': db_values[\'item_desc\'],
                        \'embarque\': db_values[\'embarque\'],
                        \'entrega\': db_values[\'entrega\'],
                        \'pecas\': db_values[\'pecas\'],
                        \'colecao\': db_values[\'colecao\'],
                        \'tamanho\': db_values[\'tamanho\'],
                        \'artigo\': db_values[\'artigo\']
                    }
                )
                db.session.execute(upsert_stmt)
                itens_processados_keys.add(item_key)

            novo_lote.total_alterados = mudancas_detectadas
            db.session.commit()

            flash(f"Processado com sucesso: {len(itens_processados_keys)} itens, {mudancas_detectadas} alterações.", "success")
            return redirect(url_for(\'detalhe_importacao\', lote_id=novo_lote.id))

        except Exception as e:
            db.session.rollback()
            print(f"ERRO: {str(e)}")
            flash(f"Erro ao processar Excel: {str(e)}", "error")
            return redirect(url_for(\'importar\'))

    return render_template(\'importar.html\')

@app.route(\'/importacoes\')
def lista_importacoes():
    lotes = ImportacaoLote.query.order_by(ImportacaoLote.data_importacao.desc()).all()
    return render_template(\'lista_importacoes.html\', lotes=lotes)

@app.route(\'/importacao/<int:lote_id>\')
def detalhe_importacao(lote_id):
    lote = ImportacaoLote.query.get_or_404(lote_id)
    mudancas = HistoricoMudanca.query.filter_by(lote_id=lote_id).all()
    return render_template(\'detalhe_importacao.html\', lote=lote, mudancas=mudancas)

@app.route(\'/historico_pedidos\')
def historico_pedidos():
    itens = PedidoItens.query.order_by(PedidoItens.ultima_atualizacao.desc()).limit(500).all()
    return render_template(\'historico_pedidos.html\', itens=itens)

@app.route(\'/periodo/<ref>\')
def visualizar_periodo(ref):
    itens = PedidoItens.query.filter_by(periodo_referencia=ref).all()
    resumo = db.session.query(
        PedidoItens.status, 
        func.sum(PedidoItens.valor_liquido), 
        func.count(PedidoItens.id)
    ).filter_by(periodo_referencia=ref).group_by(PedidoItens.status).all()
    return render_template(\'periodo.html\', itens=itens, resumo=resumo, referencia=ref)

@app.route(\'/visualizar_alterados\')
def visualizar_alterados():
    itens = PedidoItens.query.order_by(PedidoItens.ultima_atualizacao.desc()).limit(500).all()
    return render_template(\'visualizar_alterados.html\', itens=itens)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host=\'0.0.0.0\', port=port)
