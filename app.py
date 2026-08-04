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
from datetime import date
from streamlit_gsheets import GSheetsConnection

COLUNAS = ["data", "tipo", "nome", "peso_kg", "reps", "series", "duracao_min", "distancia_km"]

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
    return df


def salvar_treino(df_atual: pd.DataFrame, nova_linha: dict):
    """Adiciona um treino novo (a partir dos dados já carregados) e reescreve a aba 'treinos'."""
    df_novo = pd.concat([df_atual, pd.DataFrame([nova_linha])], ignore_index=True)
    conn.update(worksheet="treinos", data=df_novo)
    # Limpa o cache pra próxima leitura já vir com o dado novo, em vez de
    # esperar os 60 segundos do ttl.
    st.cache_data.clear()


def carregar_rotina():
    """Lê a aba 'rotina' e monta um dicionário {"A": ["Supino reto", ...], "B": [...]}."""
    df = conn.read(worksheet="rotina", ttl=60)
    df = df.dropna(how="all")

    rotina = {}
    for _, linha in df.iterrows():
        dia = linha["dia"]
        exercicio = linha["exercicio"]
        rotina.setdefault(dia, [])   # garante que o dia existe, mesmo sem exercícios
        # Uma linha "marcadora" (exercício em branco) só existe pra guardar o
        # dia vazio na planilha - não é um exercício de verdade, então não
        # entra na lista.
        if pd.notna(exercicio) and str(exercicio).strip() != "":
            rotina[dia].append(exercicio)
    return rotina


def salvar_rotina(rotina: dict):
    """Reescreve a aba 'rotina' inteira a partir do dicionário atual (uma linha por exercício)."""
    linhas = []
    for dia, exercicios in rotina.items():
        if exercicios:
            for exercicio in exercicios:
                linhas.append({"dia": dia, "exercicio": exercicio})
        else:
            # Dia sem exercícios ainda: salva uma linha "marcadora" com
            # exercício em branco, só pra planilha não esquecer que esse
            # dia existe.
            linhas.append({"dia": dia, "exercicio": ""})

    df = pd.DataFrame(linhas, columns=["dia", "exercicio"])
    conn.update(worksheet="rotina", data=df)
    st.cache_data.clear()


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
    --cor-forca: #D4A24C;   /* âmbar - musculação, cor de placa de peso */
    --cor-cardio: #4FA8A0;  /* verde-azulado - cardio */
    --cor-texto-fraco: #8B929A;
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

/* Abas com aparência de painel segmentado */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 500;
    height: 42px;
}

/* Cards de estatística estilo "placar" */
.card-placar {
    background-color: #242A31;
    border: 1px solid #333B44;
    border-top: 3px solid var(--borda-cor, var(--cor-forca));
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
    color: #EDEAE3;
}

/* Tabela e inputs com cantos levemente arredondados */
[data-testid="stDataFrame"] {
    border: 1px solid #333B44;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="cabecalho-eyebrow">Registro de treino</div>', unsafe_allow_html=True)
st.markdown('<div class="cabecalho-app">💪 Treino App</div>', unsafe_allow_html=True)
st.write("")  # respiro visual antes das abas

# st.tabs cria abas clicáveis - cada uma equivale a uma opção do menu antigo
aba_sessao, aba_rotina, aba_registrar, aba_historico, aba_estatisticas, aba_evolucao = st.tabs(
    ["🏋️ Sessão", "Minha Rotina", "Registrar", "Histórico", "Estatísticas", "Evolução"]
)

# Busca os dados da planilha UMA vez só aqui, e reaproveita nas abas abaixo.
# Antes, cada aba chamava carregar_dados()/carregar_rotina() por conta própria,
# e como o Streamlit executa o código de TODAS as abas a cada interação (não
# só a aba visível), isso gerava várias leituras repetidas por clique — o
# suficiente pra estourar o limite gratuito do Google Sheets (429 Too Many
# Requests). Buscando uma vez só e reaproveitando, cortamos isso bastante.
df_treinos = carregar_dados()
rotina = carregar_rotina()

# ---------- Aba: Sessão (modo treino guiado) ----------
with aba_sessao:
    st.caption("Escolha o treino de hoje e vá passando pelos exercícios, um de cada vez.")

    if not rotina:
        st.warning("Cadastre seu treino primeiro na aba **Minha Rotina**.")
    else:
        # st.session_state guarda informação que persiste entre as interações
        # dentro da mesma sessão do navegador (diferente de session pra session,
        # já que cada pessoa que abre o app tem o seu próprio st.session_state).
        # Aqui usamos pra lembrar qual dia foi escolhido e quais exercícios já
        # foram concluídos NESSA sessão de treino.
        if "sessao_dia" not in st.session_state:
            st.session_state.sessao_dia = None
        if "sessao_concluidos" not in st.session_state:
            st.session_state.sessao_concluidos = []
        if "sessao_ordem" not in st.session_state:
            st.session_state.sessao_ordem = []

        dia_escolhido = st.selectbox("Treino de hoje", list(rotina.keys()), key="select_dia_sessao")

        # Se trocou de dia, zera o progresso da sessão anterior e recomeça
        # a fila na ordem original cadastrada em Minha Rotina.
        if dia_escolhido != st.session_state.sessao_dia:
            st.session_state.sessao_dia = dia_escolhido
            st.session_state.sessao_concluidos = []
            st.session_state.sessao_ordem = list(rotina[dia_escolhido])

        exercicios_do_dia = rotina[dia_escolhido]

        if not exercicios_do_dia:
            st.warning(f"O treino {dia_escolhido} ainda não tem exercícios cadastrados.")
        else:
            # A fila usa "sessao_ordem" (que pode ser reorganizada ao pular um
            # exercício) em vez da lista original - assim um exercício pulado
            # vai pro final, sem perder a posição dos outros.
            pendentes = [e for e in st.session_state.sessao_ordem if e not in st.session_state.sessao_concluidos]

            total = len(exercicios_do_dia)
            feitos = len(st.session_state.sessao_concluidos)
            st.progress(feitos / total)
            st.caption(f"{feitos} de {total} exercícios concluídos")

            if not pendentes:
                st.success("🎉 Treino concluído! Mandou bem.")
                if st.button("Começar de novo"):
                    st.session_state.sessao_concluidos = []
                    st.session_state.sessao_ordem = list(exercicios_do_dia)
                    st.rerun()
            else:
                exercicio_atual = pendentes[0]
                st.subheader(f"Agora: {exercicio_atual}")

                # Botão de pular fica FORA do form (não precisa preencher nada
                # pra pular) - só reordena a fila, manda esse exercício pro final.
                if len(pendentes) > 1:
                    if st.button("⏭️ Pular por agora (equipamento ocupado)"):
                        st.session_state.sessao_ordem.remove(exercicio_atual)
                        st.session_state.sessao_ordem.append(exercicio_atual)
                        st.rerun()

                with st.form("form_sessao", clear_on_submit=True):
                    peso = st.number_input("Peso (kg)", min_value=0.0, step=2.5)
                    reps = st.number_input("Repetições por série", min_value=0, step=1)
                    series = st.number_input("Número de séries", min_value=0, step=1)
                    concluir = st.form_submit_button("✅ Concluir e ir pro próximo")

                    if concluir:
                        linha = {
                            "data": date.today(), "tipo": "musculacao", "nome": exercicio_atual,
                            "peso_kg": peso, "reps": reps, "series": series,
                            "duracao_min": "", "distancia_km": "",
                        }
                        salvar_treino(df_treinos, linha)
                        st.session_state.sessao_concluidos.append(exercicio_atual)
                        st.rerun()

                # Mostra o que já foi feito e o que ainda falta, pra ter uma visão geral
                if st.session_state.sessao_concluidos:
                    st.caption("✅ Já feito: " + ", ".join(st.session_state.sessao_concluidos))
                restantes = pendentes[1:]
                if restantes:
                    st.caption("⏳ Depois vem: " + ", ".join(restantes))

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
        for chave_dia, exercicios in rotina.items():
            with st.expander(f"🗂️ Treino {chave_dia}  ({len(exercicios)} exercícios)", expanded=False):
                # Formulário pra adicionar exercício nesse dia
                with st.form(f"form_add_exercicio_{chave_dia}", clear_on_submit=True):
                    novo_exercicio = st.text_input("Novo exercício", key=f"input_{chave_dia}")
                    adicionar = st.form_submit_button("Adicionar exercício")
                    if adicionar and novo_exercicio:
                        rotina[chave_dia].append(novo_exercicio)
                        salvar_rotina(rotina)
                        st.rerun()

                # Lista de exercícios já cadastrados, cada um com botão de remover
                if exercicios:
                    for exercicio in exercicios:
                        col_nome, col_remover = st.columns([4, 1])
                        col_nome.write(f"• {exercicio}")
                        if col_remover.button("🗑️", key=f"del_{chave_dia}_{exercicio}"):
                            rotina[chave_dia].remove(exercicio)
                            salvar_rotina(rotina)
                            st.rerun()
                else:
                    st.caption("Nenhum exercício ainda.")

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
            exercicios_do_dia = rotina[dia_escolhido]

            if not exercicios_do_dia:
                st.warning(f"O treino {dia_escolhido} ainda não tem exercícios cadastrados.")
                nome = st.text_input("Ou digite o exercício manualmente")
            else:
                # st.radio com os exercícios do dia = "clicar em qual fez"
                nome = st.radio("Qual exercício você fez?", exercicios_do_dia)

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
        # Filtro de busca simples, parecido com a opção "Buscar" do treino.py
        busca = st.text_input("🔍 Filtrar por nome do exercício/atividade")
        if busca:
            df_mostrar = df[df["nome"].str.contains(busca, case=False, na=False)]
        else:
            df_mostrar = df

        # st.dataframe já desenha uma tabela interativa (ordenável, com scroll)
        st.dataframe(df_mostrar.sort_values("data", ascending=False), use_container_width=True)

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
        card_placar(col1, "Total de registros", len(df), "#8B929A")
        card_placar(col2, "Volume total (kg)", f"{volume_total:.0f}", "#D4A24C")

        col3, col4 = st.columns(2)
        card_placar(col3, "Exercícios de musculação", len(musculacao), "#D4A24C")
        card_placar(col4, "Sessões de cardio", len(cardio), "#4FA8A0")

        card_placar(st, "Minutos totais de cardio", f"{minutos_cardio:.0f} min", "#4FA8A0")

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

