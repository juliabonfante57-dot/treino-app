"""
APP.PY - Versão web do seu app de treino, usando Streamlit
=============================================================

Streamlit transforma um script Python comum numa página web, sem
você precisar escrever HTML/CSS/JavaScript. A ideia básica:

- st.algumacoisa() desenha um elemento na tela (texto, botão, gráfico...)
- O script inteiro roda de novo, de cima a baixo, toda vez que você
  interage com algo na página (aperta um botão, muda um campo). Isso
  é diferente do treino.py, que ficava num loop esperando você digitar.

Também trocamos o módulo "csv" pelo "pandas", que lida com tabelas
de um jeito mais prático — e o Streamlit já sabe desenhar tabelas e
gráficos direto a partir de um DataFrame do pandas (é assim que se
chama uma "tabela" no pandas).

Os dados agora ficam salvos numa planilha do Google Sheets, em vez de
arquivos locais — assim eles não se perdem quando o app é publicado
na internet (o Streamlit Community Cloud não garante manter arquivos
locais entre reinicializações do servidor).
"""

import streamlit as st
import pandas as pd
import uuid        # gera um "código único" (ID) pra cada treino registrado -
                    # assim dá pra editar/excluir um específico, mesmo que
                    # dois registros pareçam idênticos (mesma data, mesmo exercício)
from datetime import date, timedelta
from streamlit_gsheets import GSheetsConnection

COLUNAS = ["id", "data", "tipo", "nome", "peso_kg", "reps", "series", "duracao_min", "distancia_km"]

# st.connection cuida de autenticar e reaproveitar a conexão entre as
# interações do app, usando as credenciais guardadas em secrets.toml.
conn = st.connection("gsheets", type=GSheetsConnection)


def carregar_dados():
    """Lê a aba 'treinos' da planilha e devolve como DataFrame do pandas."""
    # ttl=60: guarda o resultado em cache por 60 segundos, em vez de buscar
    # na planilha a cada interação. Isso evita estourar o limite gratuito
    # de leituras por minuto do Google Sheets.
    df = conn.read(worksheet="treinos", ttl=60)
    df = df.dropna(how="all")   # remove linhas totalmente vazias
    if df.empty:
        return pd.DataFrame(columns=COLUNAS)

    # Migração automática: treinos registrados antes de existir o campo "id"
    # ganham um ID novo aqui, na primeira vez que essa versão do app roda.
    if "id" not in df.columns:
        df["id"] = ""
    faltando = df["id"].isna() | (df["id"].astype(str).str.strip() == "")
    if faltando.any():
        df.loc[faltando, "id"] = [str(uuid.uuid4()) for _ in range(faltando.sum())]
        conn.update(worksheet="treinos", data=df)
        st.cache_data.clear()

    return df


def salvar_treino(df_atual: pd.DataFrame, nova_linha: dict):
    """Adiciona um treino novo (a partir dos dados já carregados) e reescreve a aba 'treinos'."""
    nova_linha["id"] = str(uuid.uuid4())
    df_novo = pd.concat([df_atual, pd.DataFrame([nova_linha])], ignore_index=True)
    conn.update(worksheet="treinos", data=df_novo)
    # Limpa o cache pra próxima leitura já vir com o dado novo, em vez de
    # esperar os 60 segundos do ttl.
    st.cache_data.clear()


def atualizar_treino(df_atual: pd.DataFrame, id_treino: str, campos_novos: dict):
    """Atualiza os campos de UM treino específico (identificado pelo id) e reescreve a planilha."""
    df_novo = df_atual.copy()
    indice = df_novo[df_novo["id"] == id_treino].index
    for campo, valor in campos_novos.items():
        df_novo.loc[indice, campo] = valor
    conn.update(worksheet="treinos", data=df_novo)
    st.cache_data.clear()


def excluir_treino(df_atual: pd.DataFrame, id_treino: str):
    """Remove UM treino específico (identificado pelo id) e reescreve a planilha."""
    df_novo = df_atual[df_atual["id"] != id_treino]
    conn.update(worksheet="treinos", data=df_novo)
    st.cache_data.clear()


def carregar_rotina():
    """Lê a aba 'rotina' e monta um dicionário {"A": [{"nome":"Supino reto","tipo":"musculacao"}, ...]}."""
    df = conn.read(worksheet="rotina", ttl=60)
    df = df.dropna(how="all")

    # Migração: planilhas antigas não tinham a coluna "tipo" (só existia
    # musculação até então) - se não existir, assume musculação pra tudo.
    if "tipo" not in df.columns:
        df["tipo"] = "musculacao"

    rotina = {}
    for _, linha in df.iterrows():
        dia = linha["dia"]
        exercicio = linha["exercicio"]
        tipo = linha["tipo"] if pd.notna(linha["tipo"]) and str(linha["tipo"]).strip() != "" else "musculacao"
        rotina.setdefault(dia, [])   # garante que o dia existe, mesmo sem exercícios
        # Uma linha "marcadora" (exercício em branco) só existe pra guardar o
        # dia vazio na planilha - não é um exercício de verdade, então não
        # entra na lista.
        if pd.notna(exercicio) and str(exercicio).strip() != "":
            rotina[dia].append({"nome": exercicio, "tipo": tipo})
    return rotina


def salvar_rotina(rotina: dict):
    """Reescreve a aba 'rotina' inteira a partir do dicionário atual (uma linha por item)."""
    linhas = []
    for dia, itens in rotina.items():
        if itens:
            for item in itens:
                linhas.append({"dia": dia, "exercicio": item["nome"], "tipo": item["tipo"]})
        else:
            # Dia sem itens ainda: salva uma linha "marcadora" com exercício
            # em branco, só pra planilha não esquecer que esse dia existe.
            linhas.append({"dia": dia, "exercicio": "", "tipo": ""})

    df = pd.DataFrame(linhas, columns=["dia", "exercicio", "tipo"])
    conn.update(worksheet="rotina", data=df)
    st.cache_data.clear()


DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]


def carregar_semana():
    """Lê a aba 'semana' e devolve {"Segunda-feira": ["A", "Corrida"], ...} - listas, já que pode ter mais de um treino no mesmo dia."""
    df = conn.read(worksheet="semana", ttl=60)
    df = df.dropna(how="all")

    plano = {dia: [] for dia in DIAS_SEMANA}
    for _, linha in df.iterrows():
        dia = linha["dia_semana"]
        treino = linha["treino"]
        if dia in plano and pd.notna(treino) and str(treino).strip() != "":
            plano[dia].append(treino)
    return plano


def salvar_semana(plano: dict):
    """Reescreve a aba 'semana' inteira (uma linha por treino escolhido em cada dia)."""
    linhas = []
    for dia, treinos in plano.items():
        if treinos:
            for treino in treinos:
                linhas.append({"dia_semana": dia, "treino": treino})
        else:
            linhas.append({"dia_semana": dia, "treino": ""})
    df = pd.DataFrame(linhas, columns=["dia_semana", "treino"])
    conn.update(worksheet="semana", data=df)
    st.cache_data.clear()


def dia_foi_cumprido(data_do_dia, treinos_planejados, rotina, df_treinos):
    """Confere se TODOS os itens dos treinos planejados pra essa data foram
    registrados nessa data. Devolve None se não havia nada planejado."""
    itens_planejados = []
    for treino in treinos_planejados:
        itens_planejados.extend(rotina.get(treino, []))

    if not itens_planejados:
        return None  # dia de descanso ou sem plano - não conta como pendência

    feitos_no_dia = df_treinos[df_treinos["data"].astype(str) == str(data_do_dia)]
    concluidos = set(zip(feitos_no_dia["tipo"], feitos_no_dia["nome"]))
    return all((item["tipo"], item["nome"]) in concluidos for item in itens_planejados)


# ---------- Configuração da página ----------
st.set_page_config(page_title="Treino App", page_icon="💪", layout="centered")

# CSS customizado: importa fontes do Google Fonts e estiliza os componentes.
# unsafe_allow_html=True é necessário pro Streamlit aceitar HTML/CSS puro.
# ATENÇÃO: com liberdade de HTML/CSS vem responsabilidade — nunca cole aqui
# CSS/HTML de fontes que você não confia.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@500;700&display=swap');

:root {
    --cor-forca: #FFC94D;    /* amarelo - musculação */
    --cor-cardio: #6EC1E4;   /* azul claro - cardio */
    --cor-primaria: #EC7FB0; /* rosa - cor principal (botões, aba ativa) */
    --cor-texto-fraco: #8D93A8;
}

/* Título principal */
.cabecalho-app {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 2.1rem;
    letter-spacing: -0.02em;
    margin-bottom: 0;
}
.cabecalho-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.15em;
    color: var(--cor-texto-fraco);
    text-transform: uppercase;
    margin-bottom: 0.2rem;
}

/* Barra de navegação fixa no topo - fica visível mesmo rolando a página,
   igual a maioria dos apps de celular de verdade. */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    position: sticky;
    top: 0;
    z-index: 999;
    background-color: #FAFAFC;
    padding: 0.6rem 0 0.8rem 0;
    border-bottom: 1px solid #E3E6ED;
}

/* Cada aba vira uma "pílula" arredondada em vez de uma aba tradicional */
.stTabs [data-baseweb="tab"] {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 500;
    font-size: 0.85rem;
    height: 38px;
    background-color: #FFFFFF;
    border: 1px solid #E3E6ED;
    border-radius: 20px;
    padding: 0 14px;
}
/* Aba ativa ganha destaque sólido na cor principal (rosa) */
.stTabs [aria-selected="true"] {
    background-color: var(--cor-primaria) !important;
    color: #FFFFFF !important;
    border-color: var(--cor-primaria) !important;
}
/* Remove aquela linha sublinhada padrão do Streamlit embaixo da aba ativa,
   já que agora o destaque é o preenchimento inteiro da pílula */
.stTabs [data-baseweb="tab-highlight"] {
    display: none;
}

/* Botões com cantos mais arredondados, mais parecido com botão de app mobile */
.stButton button, .stFormSubmitButton button {
    border-radius: 10px;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 500;
}

/* Cards de estatística estilo "placar" */
.card-placar {
    background-color: #FFFFFF;
    border: 1px solid #E3E6ED;
    border-top: 3px solid var(--borda-cor, var(--cor-primaria));
    border-radius: 6px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.6rem;
}
.card-placar .rotulo {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: var(--cor-texto-fraco);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.15rem;
}
.card-placar .valor {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1.6rem;
    color: #2B2D42;
}

/* Cards de lista (exercícios da Sessão, registros do Histórico) com cantos
   arredondados, mais parecido com "cells" de lista de um app mobile */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
}

/* Tabela e inputs com cantos levemente arredondados */
[data-testid="stDataFrame"] {
    border: 1px solid #E3E6ED;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="cabecalho-eyebrow">Registro de treino</div>', unsafe_allow_html=True)
st.markdown('<div class="cabecalho-app">💪 Treino App</div>', unsafe_allow_html=True)
st.write("")  # respiro visual antes das abas

# st.tabs cria abas clicáveis - cada uma equivale a uma opção do menu antigo
aba_sessao, aba_semana, aba_rotina, aba_registrar, aba_historico, aba_estatisticas, aba_evolucao = st.tabs(
    ["🏋️ Sessão", "📅 Semana", "🗂️ Rotina", "➕ Registrar", "📜 Histórico", "📊 Estatísticas", "📈 Evolução"]
)

# Busca os dados da planilha UMA vez só aqui, e reaproveita nas abas abaixo.
# Antes, cada aba chamava carregar_dados()/carregar_rotina() por conta própria,
# e como o Streamlit executa o código de TODAS as abas a cada interação (não
# só a aba visível), isso gerava várias leituras repetidas por clique — o
# suficiente pra estourar o limite gratuito do Google Sheets (429 Too Many
# Requests). Buscando uma vez só e reaproveitando, cortamos isso bastante.
df_treinos = carregar_dados()
rotina = carregar_rotina()
plano_semana = carregar_semana()

# Descobre o dia da semana de hoje (em português) e o treino sugerido pra
# esse dia, se houver um plano cadastrado. weekday() dá 0 pra segunda,
# 6 pra domingo - por isso a lista DIAS_SEMANA começa em "Segunda-feira".
dia_semana_hoje = DIAS_SEMANA[date.today().weekday()]
treino_sugerido_hoje = plano_semana.get(dia_semana_hoje)

# ---------- Aba: Semana (planejamento, só uma sugestão) ----------
with aba_semana:
    st.caption("Organize qual treino fazer em cada dia. É só uma sugestão pro app te lembrar - você pode sempre escolher outro na hora.")

    if not rotina:
        st.warning("Cadastre seus treinos primeiro na aba **Rotina**.")
    else:
        opcoes_semana = ["Descanso"] + list(rotina.keys())

        # --- Visão geral da semana atual: o que já foi concluído de verdade ---
        segunda_atual = date.today() - timedelta(days=date.today().weekday())
        st.write("**Essa semana**")
        colunas_semana = st.columns(7)

        for i, dia_nome in enumerate(DIAS_SEMANA):
            data_do_dia = segunda_atual + timedelta(days=i)
            treinos_planejados = [t for t in plano_semana.get(dia_nome, []) if t != "Descanso" and t in rotina]
            cumprido = dia_foi_cumprido(data_do_dia, treinos_planejados, rotina, df_treinos)

            with colunas_semana[i]:
                st.caption(dia_nome[:3])
                if cumprido is None:
                    st.write("—")  # dia de descanso ou sem plano
                elif cumprido:
                    st.write("✅")
                elif data_do_dia > date.today():
                    st.write("⏳")   # ainda não chegou o dia
                else:
                    st.write("⚠️")   # já passou e não foi concluído

        # --- Histórico: quais semanas anteriores foram batidas por completo ---
        with st.expander("📊 Histórico das últimas semanas"):
            st.caption("Compara os dias passados com o plano ATUAL - se você mudou a rotina recentemente, semanas bem antigas podem não refletir o que você pretendia treinar na época.")

            for semanas_atras in range(0, 8):
                segunda_da_semana = segunda_atual - timedelta(weeks=semanas_atras)
                domingo_da_semana = segunda_da_semana + timedelta(days=6)

                dias_com_plano = 0
                dias_cumpridos = 0
                for i, dia_nome in enumerate(DIAS_SEMANA):
                    data_do_dia = segunda_da_semana + timedelta(days=i)
                    if data_do_dia > date.today():
                        continue  # não julga dias que ainda não chegaram
                    treinos_planejados = [t for t in plano_semana.get(dia_nome, []) if t != "Descanso" and t in rotina]
                    cumprido = dia_foi_cumprido(data_do_dia, treinos_planejados, rotina, df_treinos)
                    if cumprido is not None:
                        dias_com_plano += 1
                        if cumprido:
                            dias_cumpridos += 1

                rotulo_periodo = f"{segunda_da_semana.strftime('%d/%m')} – {domingo_da_semana.strftime('%d/%m')}"
                rotulo_periodo += " (atual)" if semanas_atras == 0 else ""

                if dias_com_plano == 0:
                    st.write(f"{rotulo_periodo}: — sem treino planejado")
                elif dias_cumpridos == dias_com_plano:
                    st.write(f"{rotulo_periodo}: ✅ semana completa ({dias_cumpridos}/{dias_com_plano})")
                else:
                    st.write(f"{rotulo_periodo}: ⚠️ {dias_cumpridos}/{dias_com_plano} dias")

        st.divider()

        # --- Formulário de planejamento ---
        with st.form("form_semana"):
            novo_plano = {}
            for dia in DIAS_SEMANA:
                valores_atuais = [v for v in plano_semana.get(dia, []) if v in opcoes_semana]
                escolha = st.multiselect(dia, opcoes_semana, default=valores_atuais, key=f"semana_{dia}")
                novo_plano[dia] = escolha

            salvar = st.form_submit_button("💾 Salvar semana")
            if salvar:
                salvar_semana(novo_plano)
                st.success("Planejamento da semana atualizado!")
                st.rerun()

# ---------- Aba: Sessão (lista clicável do treino de hoje) ----------
with aba_sessao:
    st.caption("Escolha o(s) treino(s) de hoje e clique no item que você fez pra registrar.")

    if not rotina:
        st.warning("Cadastre seu treino primeiro na aba **Minha Rotina**.")
    else:
        opcoes_dia = list(rotina.keys())

        # Mostra a sugestão do plano semanal (aba Semana), se houver uma pra
        # hoje - mas é só uma sugestão: o multiselect abaixo continua livre
        # pra escolher qualquer treino, a qualquer momento. Pode ter mais de
        # um treino sugerido pro mesmo dia (ex: musculação + cardio).
        sugeridos_validos = [t for t in treino_sugerido_hoje if t in opcoes_dia]
        if sugeridos_validos:
            texto_sugestao = " e ".join(f"**{t}**" for t in sugeridos_validos)
            st.info(f"📅 Hoje é **{dia_semana_hoje}** — treino planejado: {texto_sugestao}. Mas fique à vontade pra mudar!")
        elif treino_sugerido_hoje == ["Descanso"]:
            st.info(f"📅 Hoje ({dia_semana_hoje}) você planejou descanso. Treinando mesmo assim? Escolha abaixo.")

        dias_escolhidos = st.multiselect(
            "Treino(s) de hoje", opcoes_dia, default=sugeridos_validos, key="select_dia_sessao",
        )

        if not dias_escolhidos:
            st.caption("Escolha pelo menos um treino acima pra começar.")
        else:
            # Junta os itens de todos os treinos escolhidos numa lista só
            itens_do_dia = []
            for dia in dias_escolhidos:
                itens_do_dia.extend(rotina[dia])

            if not itens_do_dia:
                st.warning("Esse(s) treino(s) ainda não têm itens cadastrados.")
            else:
                hoje = str(date.today())

                # O que já foi "concluído" é calculado a partir dos dados REAIS
                # já salvos hoje - não de uma memória temporária que se perde.
                # Combina tipo+nome pra não confundir um item de musculação
                # com um de cardio que tenha o mesmo nome por coincidência.
                feitos_hoje_df = df_treinos[df_treinos["data"].astype(str) == hoje]
                concluidos_hoje = set(zip(feitos_hoje_df["tipo"], feitos_hoje_df["nome"]))

                total = len(itens_do_dia)
                feitos = sum(1 for item in itens_do_dia if (item["tipo"], item["nome"]) in concluidos_hoje)
                st.progress(feitos / total if total else 0)
                st.caption(f"{feitos} de {total} itens concluídos hoje")

                if "exercicio_ativo" not in st.session_state:
                    st.session_state.exercicio_ativo = None

                for item in itens_do_dia:
                    nome_item = item["nome"]
                    tipo_item = item["tipo"]
                    chave_item = f"{tipo_item}_{nome_item}"
                    concluido = (tipo_item, nome_item) in concluidos_hoje
                    icone_tipo = "🏋️" if tipo_item == "musculacao" else "🏃"

                    with st.container(border=True):
                        col_nome, col_botao = st.columns([3, 1])

                        if concluido:
                            ultimo = feitos_hoje_df[
                                (feitos_hoje_df["tipo"] == tipo_item) & (feitos_hoje_df["nome"] == nome_item)
                            ].iloc[-1]
                            if tipo_item == "musculacao":
                                detalhe = f"{ultimo['peso_kg']}kg × {ultimo['reps']} reps × {ultimo['series']} séries"
                            else:
                                detalhe = f"{ultimo['duracao_min']} min" + (f" · {ultimo['distancia_km']} km" if str(ultimo['distancia_km']).strip() not in ("", "nan") else "")
                            col_nome.markdown(
                                f"✅ {icone_tipo} **{nome_item}**  \n"
                                f"<span style='color:#8D93A8;font-size:0.85rem'>{detalhe}</span>",
                                unsafe_allow_html=True,
                            )
                            rotulo_botao = "Registrar de novo"
                        else:
                            col_nome.write(f"◻️ {icone_tipo} {nome_item}")
                            rotulo_botao = "Registrar"

                        if col_botao.button(rotulo_botao, key=f"btn_sessao_{chave_item}"):
                            # Clicar de novo no mesmo item fecha o formulário
                            # (funciona como um "abre/fecha")
                            if st.session_state.exercicio_ativo == chave_item:
                                st.session_state.exercicio_ativo = None
                            else:
                                st.session_state.exercicio_ativo = chave_item
                            st.rerun()

                        if st.session_state.exercicio_ativo == chave_item:
                            with st.form(f"form_sessao_{chave_item}"):
                                if tipo_item == "musculacao":
                                    peso = st.number_input("Peso (kg)", min_value=0.0, step=2.5, key=f"peso_{chave_item}")
                                    reps = st.number_input("Repetições por série", min_value=0, step=1, key=f"reps_{chave_item}")
                                    series = st.number_input("Número de séries", min_value=0, step=1, key=f"series_{chave_item}")
                                    confirmar = st.form_submit_button("✅ Salvar")
                                    if confirmar:
                                        linha = {
                                            "data": date.today(), "tipo": "musculacao", "nome": nome_item,
                                            "peso_kg": peso, "reps": reps, "series": series,
                                            "duracao_min": "", "distancia_km": "",
                                        }
                                        salvar_treino(df_treinos, linha)
                                        st.session_state.exercicio_ativo = None
                                        st.rerun()
                                else:
                                    duracao = st.number_input("Duração (min)", min_value=0.0, step=5.0, key=f"dur_{chave_item}")
                                    distancia = st.number_input("Distância (km, opcional)", min_value=0.0, step=0.5, key=f"dist_{chave_item}")
                                    confirmar = st.form_submit_button("✅ Salvar")
                                    if confirmar:
                                        linha = {
                                            "data": date.today(), "tipo": "cardio", "nome": nome_item,
                                            "peso_kg": "", "reps": "", "series": "",
                                            "duracao_min": duracao, "distancia_km": distancia,
                                        }
                                        salvar_treino(df_treinos, linha)
                                        st.session_state.exercicio_ativo = None
                                        st.rerun()

                if feitos == total:
                    st.success("🎉 Treino concluído! Mandou bem.")

# ---------- Aba: Minha Rotina ----------
with aba_rotina:
    st.caption("Cadastre uma vez os dias e exercícios do seu treino. Depois é só clicar pra registrar.")

    # --- Criar um novo dia de treino ---
    with st.form("form_novo_dia", clear_on_submit=True):
        st.write("**Adicionar dia de treino**")
        col_a, col_b = st.columns([1, 3])
        letra_dia = col_a.text_input("Letra", placeholder="A", max_chars=3)
        nome_dia = col_b.text_input("Nome (opcional)", placeholder="Peito e tríceps")
        criar = st.form_submit_button("Criar dia")

        if criar:
            if not letra_dia:
                st.error("Digite uma letra ou nome curto pro dia (ex: A).")
            else:
                chave_dia = f"{letra_dia} - {nome_dia}" if nome_dia else letra_dia
                if chave_dia not in rotina:
                    rotina[chave_dia] = []
                    salvar_rotina(rotina)
                    st.success(f"Dia '{chave_dia}' criado!")
                    st.rerun()   # recarrega a página pra já mostrar o dia novo abaixo
                else:
                    st.warning("Esse dia já existe.")

    st.divider()

    # --- Mostrar os dias já criados, cada um numa seção expansível ---
    if not rotina:
        st.info("Nenhum dia de treino cadastrado ainda. Crie o primeiro acima.")
    else:
        atividades_cardio_comuns = ["Corrida", "Bike", "Elíptico", "Natação", "Outro"]

        for chave_dia, itens in rotina.items():
            with st.expander(f"🗂️ Treino {chave_dia}  ({len(itens)} itens)", expanded=False):
                # Formulário pra adicionar um item (musculação ou cardio) nesse dia
                with st.form(f"form_add_item_{chave_dia}", clear_on_submit=True):
                    tipo_item = st.radio(
                        "Tipo", ["Musculação", "Cardio"], horizontal=True, key=f"tipo_{chave_dia}",
                    )

                    if tipo_item == "Musculação":
                        nome_item = st.text_input("Nome do exercício", key=f"input_musc_{chave_dia}")
                    else:
                        atividade_escolhida = st.selectbox(
                            "Atividade", atividades_cardio_comuns, key=f"select_cardio_{chave_dia}",
                        )
                        nome_outro = ""
                        if atividade_escolhida == "Outro":
                            nome_outro = st.text_input("Qual atividade?", key=f"input_cardio_{chave_dia}")
                        nome_item = nome_outro if atividade_escolhida == "Outro" else atividade_escolhida

                    adicionar = st.form_submit_button("Adicionar")
                    if adicionar and nome_item:
                        tipo_salvo = "musculacao" if tipo_item == "Musculação" else "cardio"
                        rotina[chave_dia].append({"nome": nome_item, "tipo": tipo_salvo})
                        salvar_rotina(rotina)
                        st.rerun()

                # Lista de itens já cadastrados, cada um com botão de remover
                if itens:
                    for item in itens:
                        icone = "🏋️" if item["tipo"] == "musculacao" else "🏃"
                        col_nome, col_remover = st.columns([4, 1])
                        col_nome.write(f"{icone} {item['nome']}")
                        if col_remover.button("🗑️", key=f"del_{chave_dia}_{item['nome']}_{item['tipo']}"):
                            rotina[chave_dia].remove(item)
                            salvar_rotina(rotina)
                            st.rerun()
                else:
                    st.caption("Nenhum item ainda.")

                if st.button(f"Excluir treino {chave_dia}", key=f"del_dia_{chave_dia}"):
                    del rotina[chave_dia]
                    salvar_rotina(rotina)
                    st.rerun()

# ---------- Aba: Registrar ----------
with aba_registrar:
    tipo = st.radio("Tipo de treino", ["Musculação", "Cardio"], horizontal=True)

    if tipo == "Musculação":
        if not rotina:
            st.warning("Você ainda não cadastrou nenhum dia de treino. Vá na aba **Minha Rotina** primeiro.")
            nome = st.text_input("Ou digite o exercício manualmente")
        else:
            dia_escolhido = st.selectbox("Qual treino você fez hoje?", list(rotina.keys()))
            nomes_musculacao_do_dia = [item["nome"] for item in rotina[dia_escolhido] if item["tipo"] == "musculacao"]

            if not nomes_musculacao_do_dia:
                st.warning(f"O treino {dia_escolhido} ainda não tem exercícios de musculação cadastrados.")
                nome = st.text_input("Ou digite o exercício manualmente")
            else:
                # st.radio com os exercícios do dia = "clicar em qual fez"
                nome = st.radio("Qual exercício você fez?", nomes_musculacao_do_dia)

        with st.form("form_registro_musculacao", clear_on_submit=True):
            data_treino = st.date_input("Data", value=date.today())
            peso = st.number_input("Peso (kg)", min_value=0.0, step=2.5)
            reps = st.number_input("Repetições por série", min_value=0, step=1)
            series = st.number_input("Número de séries", min_value=0, step=1)
            enviado = st.form_submit_button("Salvar treino")

            if enviado:
                if not nome:
                    st.error("Escolha ou digite um exercício.")
                else:
                    linha = {
                        "data": data_treino, "tipo": "musculacao", "nome": nome,
                        "peso_kg": peso, "reps": reps, "series": series,
                        "duracao_min": "", "distancia_km": "",
                    }
                    salvar_treino(df_treinos, linha)
                    st.success(f"✅ {nome} registrado!")

    else:  # Cardio
        with st.form("form_registro_cardio", clear_on_submit=True):
            data_treino = st.date_input("Data", value=date.today())
            nome = st.text_input("Atividade (ex: Corrida, Bike)")
            duracao = st.number_input("Duração (min)", min_value=0, step=5)
            distancia = st.number_input("Distância (km)", min_value=0.0, step=0.5)
            enviado = st.form_submit_button("Salvar treino")

            if enviado:
                if not nome:
                    st.error("Preencha o nome da atividade.")
                else:
                    linha = {
                        "data": data_treino, "tipo": "cardio", "nome": nome,
                        "peso_kg": "", "reps": "", "series": "",
                        "duracao_min": duracao, "distancia_km": distancia,
                    }
                    salvar_treino(df_treinos, linha)
                    st.success(f"✅ {nome} registrado!")

# ---------- Aba: Histórico ----------
with aba_historico:
    df = df_treinos

    if df.empty:
        st.info("Ainda não há treinos registrados.")
    else:
        busca = st.text_input("🔍 Filtrar por nome do exercício/atividade")
        if busca:
            df_mostrar = df[df["nome"].str.contains(busca, case=False, na=False)]
        else:
            df_mostrar = df

        df_mostrar = df_mostrar.sort_values("data", ascending=False)

        if "editando_id" not in st.session_state:
            st.session_state.editando_id = None

        for _, linha in df_mostrar.iterrows():
            with st.container(border=True):
                if linha["tipo"] == "musculacao":
                    texto = f"**{linha['data']}** · {linha['nome']} — {linha['peso_kg']}kg × {linha['reps']} reps × {linha['series']} séries"
                else:
                    texto = f"**{linha['data']}** · {linha['nome']} (cardio) — {linha['duracao_min']} min, {linha['distancia_km']} km"

                col_info, col_editar, col_excluir = st.columns([5, 1, 1])
                col_info.markdown(texto)

                if col_editar.button("✏️", key=f"editar_{linha['id']}"):
                    st.session_state.editando_id = None if st.session_state.editando_id == linha["id"] else linha["id"]
                    st.rerun()

                if col_excluir.button("🗑️", key=f"excluir_{linha['id']}"):
                    excluir_treino(df, linha["id"])
                    st.success("Treino excluído.")
                    st.rerun()

                # Formulário de edição aparece só embaixo do registro clicado
                if st.session_state.editando_id == linha["id"]:
                    with st.form(f"form_editar_{linha['id']}"):
                        if linha["tipo"] == "musculacao":
                            novo_peso = st.number_input("Peso (kg)", min_value=0.0, step=2.5, value=float(linha["peso_kg"]))
                            novo_reps = st.number_input("Repetições", min_value=0, step=1, value=int(linha["reps"]))
                            nova_series = st.number_input("Séries", min_value=0, step=1, value=int(linha["series"]))
                            salvar = st.form_submit_button("Salvar alterações")
                            if salvar:
                                atualizar_treino(df, linha["id"], {
                                    "peso_kg": novo_peso, "reps": novo_reps, "series": nova_series,
                                })
                                st.session_state.editando_id = None
                                st.rerun()
                        else:
                            nova_duracao = st.number_input("Duração (min)", min_value=0.0, step=5.0, value=float(linha["duracao_min"] or 0))
                            distancia_atual = linha["distancia_km"]
                            nova_distancia = st.number_input(
                                "Distância (km)", min_value=0.0, step=0.5,
                                value=float(distancia_atual) if str(distancia_atual).strip() not in ("", "nan") else 0.0,
                            )
                            salvar = st.form_submit_button("Salvar alterações")
                            if salvar:
                                atualizar_treino(df, linha["id"], {
                                    "duracao_min": nova_duracao, "distancia_km": nova_distancia,
                                })
                                st.session_state.editando_id = None
                                st.rerun()


# ---------- Aba: Estatísticas ----------
with aba_estatisticas:
    df = df_treinos

    if df.empty:
        st.info("Ainda não há treinos registrados.")
    else:
        musculacao = df[df["tipo"] == "musculacao"].copy()
        cardio = df[df["tipo"] == "cardio"].copy()

        # Volume = peso x reps x séries, somado de todos os registros
        if not musculacao.empty:
            volume_total = (musculacao["peso_kg"] * musculacao["reps"] * musculacao["series"]).sum()
        else:
            volume_total = 0
        minutos_cardio = cardio["duracao_min"].sum() if not cardio.empty else 0

        # Função auxiliar: desenha um "card de placar" com a cor certa
        # (âmbar pra estatísticas de força, verde-azulado pra cardio).
        def card_placar(coluna, rotulo, valor, cor):
            coluna.markdown(f"""
                <div class="card-placar" style="--borda-cor: {cor}">
                    <div class="rotulo">{rotulo}</div>
                    <div class="valor">{valor}</div>
                </div>
            """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        card_placar(col1, "Total de registros", len(df), "#8D93A8")
        card_placar(col2, "Volume total (kg)", f"{volume_total:.0f}", "#FFC94D")

        col3, col4 = st.columns(2)
        card_placar(col3, "Exercícios de musculação", len(musculacao), "#FFC94D")
        card_placar(col4, "Sessões de cardio", len(cardio), "#6EC1E4")

        card_placar(st, "Minutos totais de cardio", f"{minutos_cardio:.0f} min", "#6EC1E4")

# ---------- Aba: Evolução ----------
with aba_evolucao:
    df = df_treinos

    if df.empty:
        st.info("Registre treinos para ver a evolução.")
    else:
        tipo_evolucao = st.radio("Tipo", ["Musculação", "Cardio"], horizontal=True, key="tipo_evolucao")

        if tipo_evolucao == "Musculação":
            musculacao = df[df["tipo"] == "musculacao"]

            if musculacao.empty:
                st.info("Registre exercícios de musculação para ver a evolução.")
            else:
                # selectbox mostra um menu suspenso com os exercícios já registrados,
                # sem o usuário ter que digitar o nome certinho
                exercicios = sorted(musculacao["nome"].unique())
                escolhido = st.selectbox("Escolha o exercício", exercicios)

                dados_exercicio = musculacao[musculacao["nome"] == escolhido].sort_values("data")

                # st.line_chart desenha o gráfico direto a partir do DataFrame -
                # não precisa nem do matplotlib aqui, o Streamlit já tem gráfico embutido
                st.line_chart(dados_exercicio.set_index("data")["peso_kg"])

                primeiro = dados_exercicio["peso_kg"].iloc[0]
                ultimo = dados_exercicio["peso_kg"].iloc[-1]
                diferenca = ultimo - primeiro
                st.write(f"Resumo: de **{primeiro}kg** para **{ultimo}kg** ({'+' if diferenca >= 0 else ''}{diferenca}kg no total)")

        else:  # Cardio
            cardio = df[df["tipo"] == "cardio"]

            if cardio.empty:
                st.info("Registre atividades de cardio para ver a evolução.")
            else:
                atividades = sorted(cardio["nome"].unique())
                escolhida = st.selectbox("Escolha a atividade", atividades)

                dados_atividade = cardio[cardio["nome"] == escolhida].sort_values("data")

                # Mostra duração e distância lado a lado, cada um com seu gráfico -
                # nem todo cardio tem distância registrada (ex: bike ergométrica),
                # então cada gráfico só aparece se tiver dado de verdade.
                tem_duracao = dados_atividade["duracao_min"].notna().any()
                tem_distancia = dados_atividade["distancia_km"].notna().any() and (dados_atividade["distancia_km"] != "").any()

                if tem_duracao:
                    st.write("**Duração (min)**")
                    st.line_chart(dados_atividade.set_index("data")["duracao_min"])

                if tem_distancia:
                    st.write("**Distância (km)**")
                    dados_com_distancia = dados_atividade[dados_atividade["distancia_km"].notna() & (dados_atividade["distancia_km"] != "")]
                    st.line_chart(dados_com_distancia.set_index("data")["distancia_km"])

                primeiro = dados_atividade["duracao_min"].iloc[0]
                ultimo = dados_atividade["duracao_min"].iloc[-1]
                diferenca = ultimo - primeiro
                st.write(f"Resumo de duração: de **{primeiro} min** para **{ultimo} min** ({'+' if diferenca >= 0 else ''}{diferenca} min no total)")

