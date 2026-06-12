# DW-AI

Sistema inteligente para auxiliar na criação de modelos dimensionais de Data Warehouse a partir de estruturas transacionais.

O DW-AI tem como objetivo analisar schemas relacionais, identificar entidades analíticas e sugerir uma modelagem dimensional seguindo boas práticas de Business Intelligence e a metodologia de Ralph Kimball.

---

## Sobre o projeto

Na construção de um Data Warehouse, uma das etapas mais importantes é transformar dados operacionais em estruturas analíticas.

Esse processo normalmente exige:

- análise de tabelas transacionais;
- identificação de fatos e dimensões;
- definição de métricas;
- criação de modelos dimensionais;
- documentação das decisões.

O DW-AI busca automatizar parte desse processo utilizando técnicas de análise estrutural e Inteligência Artificial para auxiliar engenheiros de dados e analistas na criação de modelos analíticos.

---

## Objetivo

O sistema recebe uma estrutura de banco transacional e gera uma sugestão de modelo dimensional.

Fluxo principal:

```

Schema Transacional
|
v
Análise Estrutural
|
v
Identificação de Fatos e Dimensões
|
v
Modelo Dimensional (Star Schema)

````

---

# Funcionalidades

## Análise de schema SQL

O sistema aceita estruturas SQL DDL contendo criação de tabelas.

Exemplo:

```sql
CREATE TABLE orders (
    id INT PRIMARY KEY,
    customer_id INT,
    total DECIMAL,
    created_at TIMESTAMP
);
````

---

## Extração de metadados

O DW-AI identifica:

* tabelas;
* colunas;
* tipos de dados;
* chaves primárias;
* chaves estrangeiras;
* relacionamentos.

---

## Identificação de tabelas fato

O sistema analisa características transacionais para encontrar possíveis fatos.

Exemplos:

```
sales
orders
transactions
```

Critérios analisados:

* quantidade de relacionamentos;
* presença de métricas;
* natureza histórica dos dados.

---

## Identificação de dimensões

Detecta tabelas descritivas usadas para análise.

Exemplos:

```
customers
products
stores
```

---

## Identificação de medidas

Localiza possíveis métricas analíticas:

Exemplos:

```
quantity
price
amount
total
```

---

## Geração de Star Schema

O sistema gera uma sugestão de modelo dimensional:

```json
{
    "fact_table": "fact_sales",
    "dimensions": [
        "dim_customer",
        "dim_product",
        "dim_date"
    ],
    "measures": [
        "quantity",
        "total"
    ]
}
```

---

## Explicação das decisões

Além do resultado, o sistema pode explicar as classificações.

Exemplo:

```
A tabela orders foi classificada como fato porque possui:

- múltiplas chaves estrangeiras;
- medidas numéricas;
- comportamento transacional.
```

---

# Arquitetura

O backend segue um pipeline simples:

```
        SQL DDL
           |
           v
     DDL Parser
           |
           v
   Modelo Interno
           |
           v
  Análise Dimensional
           |
           v
 Star Schema Generator
           |
           v
       JSON API
```

---

# Tecnologias

## Backend

* Python
* FastAPI
* Pydantic

## Banco de dados

* PostgreSQL (planejado)

## Inteligência Artificial

* Integração com LLM para:

  * classificação semântica;
  * explicação de decisões;
  * sugestões de melhoria.

---

# Estrutura do projeto

```
dw-ai/

├── app/
│
├── api/
│   └── endpoints da aplicação
│
├── models/
│   └── entidades do sistema
│
├── parsers/
│   └── interpretação de SQL
│
├── services/
│   ├── análise dimensional
│   ├── detecção de fatos
│   ├── detecção de dimensões
│   └── geração do modelo
│
├── ai/
│   └── integração com IA
│
├── tests/
│
└── examples/
    └── schemas SQL de exemplo
```

---

# Requisitos do sistema

## Requisitos funcionais

* Receber schema SQL;
* Interpretar tabelas e colunas;
* Identificar relacionamentos;
* Detectar fatos;
* Detectar dimensões;
* Encontrar medidas;
* Identificar dimensão temporal;
* Gerar Star Schema;
* Explicar decisões.

---

## Requisitos não funcionais

* Código modular;
* Fácil manutenção;
* Resposta rápida para schemas médios;
* Arquitetura preparada para expansão;
* Validação das entradas;
* Segurança dos dados enviados.

---

# Roadmap

## Versão 0.1

* [x] Definição da arquitetura
* [ ] Parser SQL
* [ ] Modelo interno de dados
* [ ] Detector de fatos
* [ ] Detector de dimensões
* [ ] Gerador Star Schema

---

## Versão 0.2

* [ ] API REST completa
* [ ] Persistência dos modelos
* [ ] Histórico de análises

---

## Versão 0.3

* [ ] Integração com IA
* [ ] Explicações automáticas
* [ ] Sugestões inteligentes

---

## Versão futura

* Conexão direta com bancos;
* Suporte a múltiplos SGBDs;
* Geração automática de documentação;
* Integração com ferramentas de BI.

---

# Conceitos utilizados

O projeto utiliza conceitos de:

* Data Warehouse;
* Modelagem Dimensional;
* Star Schema;
* ETL/ELT;
* Engenharia Analítica;
* Inteligência Artificial aplicada à Engenharia de Dados.

---

# Objetivo acadêmico

O DW-AI busca demonstrar como técnicas de análise estrutural e Inteligência Artificial podem auxiliar na transformação de dados transacionais em modelos analíticos, reduzindo esforço manual no processo de criação de Data Warehouses.

---

# Licença

Este projeto está em desenvolvimento para fins acadêmicos e de pesquisa.