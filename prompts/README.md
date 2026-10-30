# Prompts

Os templates foram copiados dos harnesses sem alteração de texto.

| Arquivo | Origem |
|---|---|
| `mbpp_user.txt` | EvalPlus 0.3.1: `evalplus/codegen.py` (`instruction_prefix`, prompt padrão) montado como em `evalplus/provider/anthropic.py`: `instruction_prefix + "\n```python\n" + prompt.strip() + "\n```\n"`. `{prompt}` é o campo `prompt` do MBPP+, já com `.strip()`. |
| `lcb_system.txt` | LiveCodeBench `28fef95`: `lcb_runner/prompts/code_generation.py`, `PromptConstants.SYSTEM_MESSAGE_GENERIC`, enviado como `system` (estilo `LMStyle.Claude3`). |
| `lcb_user.txt` | Mesmo arquivo, `get_generic_question_template_answer(question).rstrip()`. Reproduzido em `scripts/prompts.py`. `scripts/check_lcb_prompts.py` compara, dentro do contêiner do LCB, cada prompt com o da função original (deve dar 175/175 idênticos). Este arquivo é só uma cópia legível. |

**Desvio documentado:** o EvalPlus define também um `response_prefix` (prefill do assistente). O provider Anthropic do próprio EvalPlus não o envia, e o Claude Opus 5.5 rejeita prefill com erro 400. Por isso ele não é usado.
