# Codebook de causas prováveis (rascunho v0)

Ponto de partida para a calibração. Parte das 10 categorias de Tambon et al. (2025), com as adaptações previstas no roteiro. As definições foram parafraseadas da seção 4.1.1 da versão arXiv do artigo (2403.08937v2). **Confiram-nas com a versão publicada que vocês citam antes da calibração.** Os exemplos são genéricos: nenhum vem das falhas deste estudo, para não influenciar a codificação cega.

## Como codificar

- **Unidade:** a primeira amostra reprovada de cada problema, pela ordem de `sample_idx`. As outras amostras reprovadas são só contexto.
- **Causa principal:** exatamente uma, a que, se corrigida, faria a amostra passar na entrada que falhou.
- **Causas secundárias:** zero ou mais, separadas por `;`.
- **Manifestação não é causa:** o tipo de erro já está na planilha. A causa explica por que o erro aconteceu.
- **Etapa 1 cega:** use só o enunciado, o código, o erro e a entrada que falhou. Não consulte o resumo do raciocínio nem a planilha do outro pesquisador.

## Defeito do benchmark (decidir antes da causa)

Não é uma categoria de causa. Marque `defeito_benchmark = sim` quando o enunciado for ambíguo a ponto de admitir a solução gerada, ou quando o teste contradisser o enunciado. Se A e B marcarem `sim`, a falha sai da análise de causas e vai para uma tabela separada. Se divergirem, C decide. A coluna `suspeita_defeito_benchmark` é só uma sugestão mecânica: todas as amostras falharam na mesma entrada, com a mesma saída.

## Categorias de Tambon et al. (2025)

| Categoria | Definição operacional | Exemplo genérico |
|---|---|---|
| **Misinterpretation** | O código se desvia da intenção do enunciado, porque a especificação da tarefa não foi capturada. | Pedem o k-ésimo maior e o código devolve o k-ésimo menor. |
| **Missing Corner Case** | O código está correto no geral, mas ignora certos casos de borda. | Lista vazia, valor zero ou um único elemento. |
| **Silly Mistake** | Construções redundantes ou sem sentido, que sozinhas podem não ser defeito, mas levam facilmente a um. | Condição redundante, conversão desnecessária ou `if/else` com ramos idênticos. |
| **Incomplete Generation** | Nenhum código útil foi produzido, ou a geração parou no meio da função. | Função só com `pass`, ou corpo interrompido. |
| **Prompt-biased Code** | O código se apoia demais nos exemplos ou em termos do enunciado e só funciona para eles. | Trata como regra um padrão que só aparece no exemplo. |
| **Non-Prompted Consideration** | O código acrescenta instruções sem relação com a tarefa pedida, e isso leva ao erro. | Inclui uma validação não pedida que quebra a execução. |
| **Wrong Input Type** | Um tipo de entrada errado é passado a uma chamada de função que, fora isso, está correta. | Passa uma `str` a uma função que recebe `int`. |
| **Hallucinated Object** | O código usa uma função ou objeto que não existe e não foi definido. | Chama uma função nunca definida. |
| **Wrong Attribute** | O código acessa um atributo incorreto ou inexistente de um objeto ou módulo. | Chama um método inexistente em `str`. |
| **Syntax Error** | No artigo, qualquer violação da sintaxe da linguagem. Aqui é tratada como **manifestação**, não como causa. Codifique o que levou ao erro; *Incomplete Generation* costuma cobrir esses casos. | Não usar como causa. |

*Silly Mistake* não cobre deslizes de lógica como limites deslocados em um. A calibração deve decidir onde eles entram, por exemplo em *Algoritmo incorreto*, ou se pedem uma categoria nova.

*Hallucinated Object* e *Wrong Attribute* são pouco prováveis em problemas que usam só a biblioteca padrão. Elas ficam no codebook, e a raridade delas é reportada como resultado.

## Categorias candidatas para programação competitiva

A confirmar na calibração.

| Categoria | Definição operacional | Exemplo genérico |
|---|---|---|
| **Algoritmo incorreto** | O enunciado foi entendido, mas a estratégia não resolve o problema. | Guloso onde o ótimo exige programação dinâmica. |
| **Complexidade insuficiente** | A lógica está correta, mas a ordem de complexidade não comporta os limites do problema. | Solução O(n²) para n = 10⁵. |

## Categorias novas

Registre aqui as categorias que surgirem, com a data e a falha que motivou cada uma.

| Data | Categoria | Definição | Falha que motivou |
|---|---|---|---|

## Histórico de alterações

| Versão | Data | Alteração |
|---|---|---|
| v0 | 2026-10-31 | Rascunho inicial, antes da calibração, com definições conferidas na versão arXiv do artigo. |
