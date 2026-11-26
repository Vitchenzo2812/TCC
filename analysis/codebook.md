# Codebook de causas prováveis (versão final, v2)

Instrumento de codificação das falhas funcionais do Claude Opus 5.5. Parte das 10 categorias de Tambon et al. (2025), com definições parafraseadas da seção 4.1.1 do artigo e conferidas com a versão arXiv (2403.08937v2), e acrescenta duas categorias para programação competitiva.

As **definições das categorias** são as mesmas usadas na etapa 1 (Quadro 10 do ATCC). Esta versão acrescenta apenas esclarecimentos que surgiram na calibração e na reconciliação. Esses esclarecimentos descrevem como as decisões foram tomadas e **não serviram para recodificar a etapa 1**.

## Papéis

- **Codificador A:** Iris Helen de Brito Pires.
- **Codificador B:** Guilherme Vitchenzo Penas.
- Não houve terceiro codificador. As divergências seguem a regra de reconciliação descrita abaixo.
- Nenhuma ferramenta de IA atribuiu causas nem decidiu defeitos do benchmark. Essas decisões são dos codificadores.

## Como codificar

- **Unidade:** a primeira amostra reprovada de cada problema, pela ordem de `sample_idx`. As outras amostras reprovadas servem só de contexto.
- **Ordem:**
  1. Leia o enunciado e o código.
  2. Examine a falha: manifestação, entrada que falhou, saída esperada e saída obtida.
  3. Decida se há defeito do benchmark.
  4. Só então, se não houver defeito, atribua a causa.
- **Causa principal:** exatamente uma, aquela que, se corrigida, faria a amostra passar na entrada que falhou.
- **Causas secundárias:** zero ou mais, separadas por `;`.
- **Justificativa:** descreva o diagnóstico de forma verificável, citando o trecho do código, a entrada e a saída. Não registre grau de confiança.
- **Manifestação não é causa:** o tipo de erro já vem na planilha. A causa explica por que o erro aconteceu.

## Defeito do benchmark (decidir antes da causa)

Não é uma categoria de causa. Marque `defeito_benchmark = sim` quando o enunciado for ambíguo a ponto de admitir a solução gerada, ou quando o teste contradisser o enunciado. Nesses casos, a falha sai da análise de causas e vai para uma tabela separada (Apêndice C do ATCC).

A coluna `suspeita_defeito_benchmark` é só uma sugestão mecânica: indica que todas as amostras falharam na mesma entrada, com a mesma saída. Ela não decide nada.

**Esclarecimento (calibração e reconciliação).** Os casos abaixo foram tratados como teste que contradiz o enunciado. São os tipos que apareceram nos defeitos confirmados por execução:

| Situação | Exemplo do critério |
|---|---|
| Tolerância numérica declarada e não aplicada | O enunciado aceita erro de até 10⁻⁶, mas a saída foi comparada como texto. |
| Entrada fora das restrições do enunciado | A entrada que falhou viola um limite declarado, como `1 <= nums[i] <= n`. |
| Resposta alternativa válida | O enunciado aceita qualquer solução ótima, e o teste exige uma solução específica. |
| Falha do ambiente de avaliação | O código lê a entrada padrão real (`open(0)`), e o harness a substitui por `StringIO`. |
| Restrição não declarada | O teste exige uma condição que o enunciado não menciona. |

Um módulo externo que não existe no ambiente de avaliação **não** é defeito do benchmark: conta como *Hallucinated Object*, pela decisão final da reconciliação.

## Categorias de Tambon et al. (2025)

| Categoria | Definição operacional | Exemplo genérico |
|---|---|---|
| **Misinterpretation** | O código se desvia da intenção do enunciado, porque a especificação da tarefa não foi capturada. | Pedem o k-ésimo maior e o código devolve o k-ésimo menor. |
| **Missing Corner Case** | O código está correto no geral, mas ignora certos casos de borda. | Lista vazia, valor zero ou um único elemento. |
| **Silly Mistake** | Construções redundantes ou sem sentido, que sozinhas podem não ser defeito, mas levam facilmente a um. | Condição redundante, conversão desnecessária ou `if/else` com ramos idênticos. |
| **Incomplete Generation** | Nenhum código útil foi produzido, ou a geração parou no meio da função. | Função só com `pass`, ou corpo interrompido. |
| **Prompt-biased Code** | O código se apoia demais nos exemplos ou nos termos do enunciado e só funciona para eles. | Trata como regra um padrão que só aparece no exemplo. |
| **Non-Prompted Consideration** | O código acrescenta instruções sem relação com a tarefa pedida, e isso leva ao erro. | Inclui uma validação não pedida que quebra a execução. |
| **Wrong Input Type** | Um tipo de entrada errado é passado a uma chamada de função que, fora isso, está correta. | Passa uma `str` a uma função que recebe `int`. |
| **Hallucinated Object** | O código usa uma função ou objeto que não existe e não foi definido. | Chama uma função nunca definida, ou importa um módulo indisponível no ambiente. |
| **Wrong Attribute** | O código acessa um atributo incorreto ou inexistente de um objeto ou módulo. | Chama um método inexistente em `str`. |
| **Syntax Error** | No artigo, qualquer violação da sintaxe da linguagem. Aqui é tratada como **manifestação**, não como causa. | Não usar como causa: codifique o que levou ao erro (*Incomplete Generation* costuma cobrir esses casos). |

## Categorias acrescentadas para programação competitiva

Confirmadas na calibração.

| Categoria | Definição operacional | Exemplo genérico |
|---|---|---|
| **Algoritmo incorreto** | O enunciado foi entendido, mas a estratégia não resolve o problema. | Guloso onde o ótimo exige programação dinâmica. |
| **Complexidade insuficiente** | A lógica está correta, mas a ordem de complexidade não comporta os limites do problema. | Solução O(n²) para n = 10⁵. |

## Fronteira de *Silly Mistake*

A definição de Tambon et al. (2025) cobre só construções redundantes ou sem sentido. Ela não diz onde entram os **deslizes pontuais de lógica**: índice deslocado em um, comparação ou sinal invertido, linha de atualização esquecida.

A calibração não fixou essa fronteira, e ela concentrou as divergências de causa: em 7 das 12, um codificador usou *Silly Mistake* para um desses deslizes, e o outro usou *Algoritmo incorreto*, *Misinterpretation* ou *Missing Corner Case*. Na reconciliação, B concluiu que a própria classificação, apoiada em *Silly Mistake* na maioria dos casos, não se ajustava às falhas de maior complexidade, e a decisão de A prevaleceu.

> **Esclarecimento aprovado por A e B (2026-11-26).**
> *Silly Mistake* inclui o deslize pontual de implementação quando a estratégia do código está correta e a falha se corrige alterando só um trecho local (operador, sinal, índice ou limite), sem mudar a estratégia. Se a correção exige mudar a estratégia, use *Algoritmo incorreto*. Se o deslize vem de uma leitura errada do enunciado, use *Misinterpretation*.

O esclarecimento foi aprovado depois da reconciliação. As decisões finais do estudo **não foram recodificadas** por ele, e seguem a regra de reconciliação. Ele vale para codificações futuras com este codebook.

## Etapas e cegamento

- **Calibração:** A e B codificaram separadamente as 11 falhas reservadas e compararam as respostas. As duas categorias candidatas foram mantidas, e não foi necessário criar categorias novas. As falhas da calibração não entram nos resultados.
- **Etapa 1 (independente):**
  - Cada codificador usa só a própria planilha.
  - As falhas não são discutidas entre os codificadores.
  - Os resumos do raciocínio só são abertos depois do cálculo da concordância.
  - Depois desse cálculo, as planilhas da etapa 1 não mudam mais.
  - **Desvio declarado:** A leu os resumos do raciocínio antes de concluir a etapa 1, e 15 justificativas de A os citam. A etapa 1 de B foi cega.
- **Normalização:** A respondeu em texto livre. B converteu esse texto nas categorias deste codebook, e A revisou e aprovou a conversão.
- **Etapa 2:** depois da concordância, cada codificador lê o resumo do raciocínio e registra se ele mudaria a causa. A etapa 2 não altera a etapa 1 nem o Kappa. Quando não há resumo, registre "sem raciocínio nesta amostra".

## Verificação por execução

B verificou por execução os diagnósticos que dependiam de um fato objetivo:

- se a saída respeitava a tolerância declarada;
- se uma resposta diferente era igualmente válida;
- se a entrada respeitava as restrições;
- se o código passava com a entrada padrão real;
- se o código ou o gabarito concordavam com uma força bruta.

As verificações estão em `analysis/verificacoes/`. O script foi escrito com auxílio de IA, mas a IA não decidiu nenhuma causa nem defeito: o script só confere fatos.

## Concordância e reconciliação

- **Kappa de Cohen** sobre a causa principal da etapa 1 e sobre a decisão de defeito (sim ou não). Para a causa, ficam fora as falhas que ambos marcaram como defeito e as que só um marcou; estas vão direto à reconciliação.
- **Reconciliação:**
  - Onde A e B concordam, vale a resposta comum.
  - Onde divergem, prevalece a resposta de A.
  - **Exceção:** em F063, F077, F078 e F082, B apontou defeito do benchmark e A não. A verificação por execução confirmou o defeito, e a decisão final seguiu essa evidência.
- A regra está implementada em `scripts/reconcile.py`, e cada decisão registra sua origem em `data/processed/coding/reconciliacao.csv`.

## Categorias novas

Nenhuma categoria nova foi criada.

| Data | Categoria | Definição | Falha que motivou |
|---|---|---|---|
| – | – | – | – |

## Histórico de alterações

| Versão | Data | Alteração |
|---|---|---|
| v0 | 2026-10-31 | Rascunho inicial, antes da calibração, com definições conferidas com a versão arXiv do artigo. |
| v1 | 2026-11-21 | Calibração: as categorias *Algoritmo incorreto* e *Complexidade insuficiente* foram confirmadas, sem categorias novas e sem mudança nas definições. Versão usada na etapa 1 (Quadro 10 do ATCC). |
| v2 | 2026-11-26 | Versão final, sem mudança nas definições da v1. Acrescenta: papéis; regra de reconciliação e exceção por execução; tipos de defeito do benchmark; módulo indisponível como *Hallucinated Object*; desvios de cegamento e normalização; esclarecimento da fronteira de *Silly Mistake*, aprovado por A e B. |
