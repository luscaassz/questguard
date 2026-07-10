# QuestGuard

Arquitetura modular de quality gates para geração, validação, reparo e análise de quests produzidas por LLMs.

## 1. O que mudou em relação aos scripts originais

O projeto foi dividido em componentes com responsabilidades explícitas:

```text
WorldRepository ──► GenerationService ──► Schema Gate
                                           │
                                           ▼
                                  Referential Gate
                                           │
                                           ▼
                                     Graph Gate
                                           │
                                           ▼
                                    Semantic Gate
                                           │
                          aprovado ────────┴──── rejeitado
                              │                       │
                              ▼                       ▼
                     Artifact Repository      Repair Orchestrator
                                                      │
                                                      └──► revalidação
```

A arquitetura oferece:

- abstração do cliente de LLM;
- JSON Schema realmente executado;
- integridade referencial por categoria de entidade;
- compatibilidade entre ação e tipo de alvo;
- validação de dependências entre objetivos;
- detecção de ciclos e referências a etapas inexistentes;
- avaliação semântica opcional;
- reparo automático com revalidação;
- métricas de grafo e diversidade;
- injeção de falhas para Precision, Recall e F1;
- comparação experimental C1–C4.

## 2. Estrutura

```text
questguard_project/
├── data/
│   ├── world.json
│   ├── quest_schema.json
│   └── example_valid_quest.json
├── questguard/
│   ├── adapters/          # Ollama e parser robusto de JSON
│   ├── analysis/          # grafos, métricas e revisão coletiva
│   ├── domain/            # entidades, issues e relatórios
│   ├── experiments/       # fault injection e avaliação
│   ├── generation/        # prompts e serviços de geração
│   ├── orchestration/     # pipeline completo
│   ├── ports/             # interfaces independentes de provedor
│   ├── repair/            # reparo e revalidação
│   ├── repositories/      # modelo do mundo
│   ├── reports/           # JSON, CSV e texto
│   └── validation/        # quality gates
├── scripts/
│   ├── 00_smoke_test.py
│   ├── 01_generate.py
│   ├── 02_validate.py
│   ├── 03_repair.py
│   ├── 04_analyze.py
│   ├── 05_run_pipeline.py
│   ├── 06_fault_injection.py
│   ├── 07_set_review.py
│   └── 08_compare_configurations.py
└── tests/
```

## 3. Instalação

Recomenda-se Python 3.10 ou superior.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Instale o pacote e as dependências:

```bash
pip install -e .
pip install pytest
```

Instale e inicie o Ollama:

```bash
ollama pull llama3.2
ollama serve
```

## 4. Passo 0 — testar sem usar LLM

```bash
python scripts/00_smoke_test.py
pytest -q
```

O projeto entregue possui 12 testes automatizados.

## 5. Passo 1 — substituir os dados de exemplo

Copie seu `world.json` para:

```text
data/world.json
```

Ajuste `data/quest_schema.json` conforme os campos das suas quests.

Categorias reconhecidas pelo repositório:

```text
npcs, locations, items, factions, enemies, objects
```

IDs não podem se repetir entre categorias.

## 6. Passo 2 — gerar quests

Teste pequeno:

```bash
python scripts/01_generate.py --batches 1 --quests-per-batch 3
```

Experimento completo:

```bash
python scripts/01_generate.py --batches 10 --quests-per-batch 10
```

Saídas:

```text
outputs/quests.json
outputs/quest_batches/
outputs/raw_responses/
```

## 7. Passo 3 — executar quality gates

Somente validações determinísticas:

```bash
python scripts/02_validate.py
```

Incluindo avaliação semântica por LLM:

```bash
python scripts/02_validate.py --semantic
```

Saídas:

```text
outputs/validation_report.json
outputs/validation_summary.json
```

## 8. Passo 4 — reparar quests rejeitadas

```bash
python scripts/03_repair.py
```

Incluindo a avaliação semântica no ciclo de reparo:

```bash
python scripts/03_repair.py --semantic
```

Saídas:

```text
outputs/accepted_quests.json
outputs/rejected_quests.json
outputs/repair_report.json
outputs/repair_raw_responses/
```

## 9. Passo 5 — calcular métricas

```bash
python scripts/04_analyze.py
```

Métricas produzidas:

- número de nós e arestas;
- densidade;
- profundidade;
- referências ao mundo;
- entidades implícitas;
- entropia de tipos de quest;
- cobertura e concentração de entidades;
- assinaturas estruturais duplicadas;
- similaridade média entre quests.

Saídas:

```text
outputs/quest_graph_metrics.csv
outputs/quest_set_metrics.json
```

## 10. Passo 6 — executar tudo em uma chamada

```bash
python scripts/05_run_pipeline.py \
  --batches 10 \
  --quests-per-batch 10 \
  --repair \
  --semantic
```

Para uma primeira execução, use apenas um batch com três quests.

## 11. Passo 7 — experimento de injeção de falhas

```bash
python scripts/06_fault_injection.py --limit 20
```

Falhas injetadas:

1. campo obrigatório removido;
2. alvo inexistente;
3. item usado como quest giver;
4. `step_id` duplicado;
5. dependência inexistente;
6. ciclo entre objetivos;
7. condição de conclusão genérica.

Saídas:

```text
outputs/fault_mutants.json
outputs/fault_detection_evaluation.json
```

O segundo arquivo contém Precision, Recall e F1 por validador.

## 12. Passo 8 — avaliação do conjunto

```bash
python scripts/07_set_review.py
```

Essa etapa combina métricas determinísticas com uma revisão qualitativa pelo LLM.

## 13. Passo 9 — comparação C1–C4

Comece com configuração pequena:

```bash
python scripts/08_compare_configurations.py \
  --batches 2 \
  --quests-per-batch 5
```

Configurações:

- **C1 Prompt-only:** prompt simples, sem schema ou quality gates;
- **C2 Schema-guided:** schema e regras no prompt;
- **C3 Quality gates:** C2 com rejeição de artefatos inválidos;
- **C4 Quality gates + repair:** C3 com reparo e revalidação.

Saída:

```text
outputs/configuration_comparison.json
```

## 14. Como adicionar um novo quality gate

Crie uma classe que implemente `QuestValidator`:

```python
from questguard.domain.issues import Issue, ValidationReport
from questguard.validation.base import QuestValidator

class AccessibilityValidator(QuestValidator):
    name = "accessibility"

    def validate(self, quest):
        report = ValidationReport(validator=self.name)
        # adicionar issues ao relatório
        return report
```

Depois registre a classe em `questguard/bootstrap.py`.

## 15. Como trocar o provedor de LLM

Implemente `LLMClient` em `questguard/ports/llm.py`. Nenhum validador precisa ser alterado.

Essa separação é uma das principais evidências de extensibilidade e baixo acoplamento da arquitetura.

## 16. Resultados recomendados para o artigo

Use pelo menos:

- validade estrutural e referencial de C1–C4;
- taxa de aprovação inicial;
- taxa de sucesso do reparo;
- número médio de tentativas;
- Precision, Recall e F1 na injeção de falhas;
- cobertura de entidades;
- entropia dos tipos de quest;
- taxa de assinaturas duplicadas;
- latência e quantidade de chamadas ao LLM;
- avaliação humana de uma amostra estratificada.

## 17. Limitações atuais

- o repositório reconhece apenas as categorias declaradas em `CATEGORY_TO_TYPE`;
- condições ainda são representadas principalmente como texto;
- a revisão semântica pode variar entre execuções;
- os experimentos com LLM não definem seed porque o suporte depende do backend/modelo;
- a comparação C1–C4 tem custo proporcional ao número de quests geradas.
