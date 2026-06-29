# 30-Language RAG Matrix E2E Report
**Generated**: 2026-05-17T12:23:14.740159+00:00
**Languages**: 30
**Combinations**: 200
**RAG DB checks**: 1200/1200
**Public provider lookups**: 600/600

## Collections Seeded
| Collection | Records |
|---|---:|
| `gitlab_successful_template` | 200 |
| `gitlab_successful_pipelines` | 200 |
| `jenkins_successful_pipelines` | 200 |
| `jenkins_pipeline_templates` | 200 |
| `gitea_actions_successful_pipelines` | 200 |
| `gitea_actions_templates` | 200 |

## Language Summary
| Language | Versions | Framework + Build Tools | Combos | GitLab | Jenkins | Gitea |
|---|---|---|---:|---:|---:|---:|
| java | 8, 11, 17, 21, 26 | generic (javac 21); gradle (gradle 8.12); maven (maven 3.9); quarkus (maven 3.9); spring-boot (maven 3.9) | 25 | 25 | 25 | 25 |
| python | 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14 | celery (poetry 2.1); django (poetry 2.1); fastapi (uv 0.8); flask (pip 25); generic (pip 25); streamlit (pip 25) | 42 | 42 | 42 | 42 |
| javascript | 18, 20, 22 | express (npm 10); generic (npm 10); react (pnpm 9) | 9 | 9 | 9 | 9 |
| typescript | 18, 20, 22 | generic (npm 10); nestjs (pnpm 9); nextjs (yarn 4) | 9 | 9 | 9 | 9 |
| go | 1.21, 1.22, 1.23 | fiber (go 1.23); generic (go 1.23); gin (go 1.23) | 9 | 9 | 9 | 9 |
| rust | 1.89, 1.93 | actix (cargo 1.93); axum (cargo 1.93); generic (cargo 1.93) | 6 | 6 | 6 | 6 |
| ruby | 3.2, 3.3, 3.4 | generic (bundle 2.5); rails (bundle 2.5) | 6 | 6 | 6 | 6 |
| php | 8.2, 8.3, 8.4 | generic (composer 2.8); laravel (composer 2.8) | 6 | 6 | 6 | 6 |
| dotnet | 8.0, 9.0 | aspnet (dotnet 9.0); generic (dotnet 9.0) | 4 | 4 | 4 | 4 |
| kotlin | 1.9, 2.0 | generic (gradle 8.12); spring-boot (gradle 8.12) | 4 | 4 | 4 | 4 |
| scala | 3.3, 2.13 | akka (sbt 1.10); generic (sbt 1.10) | 4 | 4 | 4 | 4 |
| swift | 5.9, 6.0 | generic (swiftpm 6.0); vapor (swiftpm 6.0) | 4 | 4 | 4 | 4 |
| dart | 3.4, 3.5 | flutter (pub 3.5); shelf (pub 3.5) | 4 | 4 | 4 | 4 |
| c | 17, 23 | cmake (cmake 3.30); generic (make 4.4) | 4 | 4 | 4 | 4 |
| cpp | 20, 23 | cmake (cmake 3.30); generic (make 4.4) | 4 | 4 | 4 | 4 |
| perl | 5.38, 5.40 | dancer (cpanm 1.7047); generic (cpanm 1.7047) | 4 | 4 | 4 | 4 |
| r | 4.3, 4.4 | generic (renv 1.1); shiny (renv 1.1) | 4 | 4 | 4 | 4 |
| julia | 1.10, 1.11 | generic (pkg 1.11); genie (pkg 1.11) | 4 | 4 | 4 | 4 |
| elixir | 1.16, 1.17 | generic (mix 1.17); phoenix (mix 1.17) | 4 | 4 | 4 | 4 |
| erlang | 26, 27 | cowboy (rebar3 3.24); generic (rebar3 3.24) | 4 | 4 | 4 | 4 |
| clojure | 1.11, 1.12 | generic (deps.edn 1.12); ring (leiningen 2.11) | 4 | 4 | 4 | 4 |
| groovy | 4.0, 5.0 | generic (gradle 8.12); grails (gradle 8.12) | 4 | 4 | 4 | 4 |
| lua | 5.4, luajit-2.1 | generic (luarocks 3.11); lapis (luarocks 3.11) | 4 | 4 | 4 | 4 |
| haskell | 9.6, 9.8 | generic (stack 2.15); servant (cabal 3.12) | 4 | 4 | 4 | 4 |
| nim | 2.0, 2.2 | generic (nimble 0.16); jester (nimble 0.16) | 4 | 4 | 4 | 4 |
| zig | 0.13, 0.14 | generic (zig 0.14); httpz (zig 0.14) | 4 | 4 | 4 | 4 |
| crystal | 1.12, 1.13 | generic (shards 0.17); kemal (shards 0.17) | 4 | 4 | 4 | 4 |
| ocaml | 5.1, 5.2 | dream (dune 3.16); generic (dune 3.16) | 4 | 4 | 4 | 4 |
| fsharp | 8.0, 9.0 | generic (dotnet 9.0); giraffe (dotnet 9.0) | 4 | 4 | 4 | 4 |
| bash | 5.1, 5.2 | bats (bats 1.11); generic (make 4.4) | 4 | 4 | 4 | 4 |

## Full Combination Table
| # | Language | Version | Framework | Build Tool | Stored RAG Framework | Saved | GitLab | Jenkins | Gitea | Actual CI Pipeline |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | java | 8 | generic | javac 21 | `generic-javac-java8` | PASS | PASS | PASS | PASS | not_triggered |
| 2 | java | 8 | maven | maven 3.9 | `maven-maven-java8` | PASS | PASS | PASS | PASS | not_triggered |
| 3 | java | 8 | gradle | gradle 8.12 | `gradle-gradle-java8` | PASS | PASS | PASS | PASS | not_triggered |
| 4 | java | 8 | spring-boot | maven 3.9 | `spring-boot-maven-java8` | PASS | PASS | PASS | PASS | not_triggered |
| 5 | java | 8 | quarkus | maven 3.9 | `quarkus-maven-java8` | PASS | PASS | PASS | PASS | not_triggered |
| 6 | java | 11 | generic | javac 21 | `generic-javac-java11` | PASS | PASS | PASS | PASS | not_triggered |
| 7 | java | 11 | maven | maven 3.9 | `maven-maven-java11` | PASS | PASS | PASS | PASS | not_triggered |
| 8 | java | 11 | gradle | gradle 8.12 | `gradle-gradle-java11` | PASS | PASS | PASS | PASS | not_triggered |
| 9 | java | 11 | spring-boot | maven 3.9 | `spring-boot-maven-java11` | PASS | PASS | PASS | PASS | not_triggered |
| 10 | java | 11 | quarkus | maven 3.9 | `quarkus-maven-java11` | PASS | PASS | PASS | PASS | not_triggered |
| 11 | java | 17 | generic | javac 21 | `generic-javac-java17` | PASS | PASS | PASS | PASS | not_triggered |
| 12 | java | 17 | maven | maven 3.9 | `maven-maven-java17` | PASS | PASS | PASS | PASS | not_triggered |
| 13 | java | 17 | gradle | gradle 8.12 | `gradle-gradle-java17` | PASS | PASS | PASS | PASS | not_triggered |
| 14 | java | 17 | spring-boot | maven 3.9 | `spring-boot-maven-java17` | PASS | PASS | PASS | PASS | not_triggered |
| 15 | java | 17 | quarkus | maven 3.9 | `quarkus-maven-java17` | PASS | PASS | PASS | PASS | not_triggered |
| 16 | java | 21 | generic | javac 21 | `generic-javac-java21` | PASS | PASS | PASS | PASS | not_triggered |
| 17 | java | 21 | maven | maven 3.9 | `maven-maven-java21` | PASS | PASS | PASS | PASS | not_triggered |
| 18 | java | 21 | gradle | gradle 8.12 | `gradle-gradle-java21` | PASS | PASS | PASS | PASS | not_triggered |
| 19 | java | 21 | spring-boot | maven 3.9 | `spring-boot-maven-java21` | PASS | PASS | PASS | PASS | not_triggered |
| 20 | java | 21 | quarkus | maven 3.9 | `quarkus-maven-java21` | PASS | PASS | PASS | PASS | not_triggered |
| 21 | java | 26 | generic | javac 21 | `generic-javac-java26` | PASS | PASS | PASS | PASS | not_triggered |
| 22 | java | 26 | maven | maven 3.9 | `maven-maven-java26` | PASS | PASS | PASS | PASS | not_triggered |
| 23 | java | 26 | gradle | gradle 8.12 | `gradle-gradle-java26` | PASS | PASS | PASS | PASS | not_triggered |
| 24 | java | 26 | spring-boot | maven 3.9 | `spring-boot-maven-java26` | PASS | PASS | PASS | PASS | not_triggered |
| 25 | java | 26 | quarkus | maven 3.9 | `quarkus-maven-java26` | PASS | PASS | PASS | PASS | not_triggered |
| 26 | python | 3.8 | generic | pip 25 | `generic-pip-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 27 | python | 3.8 | fastapi | uv 0.8 | `fastapi-uv-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 28 | python | 3.8 | django | poetry 2.1 | `django-poetry-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 29 | python | 3.8 | flask | pip 25 | `flask-pip-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 30 | python | 3.8 | streamlit | pip 25 | `streamlit-pip-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 31 | python | 3.8 | celery | poetry 2.1 | `celery-poetry-python3-8` | PASS | PASS | PASS | PASS | not_triggered |
| 32 | python | 3.9 | generic | pip 25 | `generic-pip-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 33 | python | 3.9 | fastapi | uv 0.8 | `fastapi-uv-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 34 | python | 3.9 | django | poetry 2.1 | `django-poetry-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 35 | python | 3.9 | flask | pip 25 | `flask-pip-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 36 | python | 3.9 | streamlit | pip 25 | `streamlit-pip-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 37 | python | 3.9 | celery | poetry 2.1 | `celery-poetry-python3-9` | PASS | PASS | PASS | PASS | not_triggered |
| 38 | python | 3.10 | generic | pip 25 | `generic-pip-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 39 | python | 3.10 | fastapi | uv 0.8 | `fastapi-uv-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 40 | python | 3.10 | django | poetry 2.1 | `django-poetry-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 41 | python | 3.10 | flask | pip 25 | `flask-pip-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 42 | python | 3.10 | streamlit | pip 25 | `streamlit-pip-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 43 | python | 3.10 | celery | poetry 2.1 | `celery-poetry-python3-10` | PASS | PASS | PASS | PASS | not_triggered |
| 44 | python | 3.11 | generic | pip 25 | `generic-pip-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 45 | python | 3.11 | fastapi | uv 0.8 | `fastapi-uv-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 46 | python | 3.11 | django | poetry 2.1 | `django-poetry-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 47 | python | 3.11 | flask | pip 25 | `flask-pip-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 48 | python | 3.11 | streamlit | pip 25 | `streamlit-pip-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 49 | python | 3.11 | celery | poetry 2.1 | `celery-poetry-python3-11` | PASS | PASS | PASS | PASS | not_triggered |
| 50 | python | 3.12 | generic | pip 25 | `generic-pip-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 51 | python | 3.12 | fastapi | uv 0.8 | `fastapi-uv-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 52 | python | 3.12 | django | poetry 2.1 | `django-poetry-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 53 | python | 3.12 | flask | pip 25 | `flask-pip-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 54 | python | 3.12 | streamlit | pip 25 | `streamlit-pip-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 55 | python | 3.12 | celery | poetry 2.1 | `celery-poetry-python3-12` | PASS | PASS | PASS | PASS | not_triggered |
| 56 | python | 3.13 | generic | pip 25 | `generic-pip-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 57 | python | 3.13 | fastapi | uv 0.8 | `fastapi-uv-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 58 | python | 3.13 | django | poetry 2.1 | `django-poetry-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 59 | python | 3.13 | flask | pip 25 | `flask-pip-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 60 | python | 3.13 | streamlit | pip 25 | `streamlit-pip-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 61 | python | 3.13 | celery | poetry 2.1 | `celery-poetry-python3-13` | PASS | PASS | PASS | PASS | not_triggered |
| 62 | python | 3.14 | generic | pip 25 | `generic-pip-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 63 | python | 3.14 | fastapi | uv 0.8 | `fastapi-uv-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 64 | python | 3.14 | django | poetry 2.1 | `django-poetry-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 65 | python | 3.14 | flask | pip 25 | `flask-pip-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 66 | python | 3.14 | streamlit | pip 25 | `streamlit-pip-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 67 | python | 3.14 | celery | poetry 2.1 | `celery-poetry-python3-14` | PASS | PASS | PASS | PASS | not_triggered |
| 68 | javascript | 18 | generic | npm 10 | `generic-npm-javascript18` | PASS | PASS | PASS | PASS | not_triggered |
| 69 | javascript | 18 | express | npm 10 | `express-npm-javascript18` | PASS | PASS | PASS | PASS | not_triggered |
| 70 | javascript | 18 | react | pnpm 9 | `react-pnpm-javascript18` | PASS | PASS | PASS | PASS | not_triggered |
| 71 | javascript | 20 | generic | npm 10 | `generic-npm-javascript20` | PASS | PASS | PASS | PASS | not_triggered |
| 72 | javascript | 20 | express | npm 10 | `express-npm-javascript20` | PASS | PASS | PASS | PASS | not_triggered |
| 73 | javascript | 20 | react | pnpm 9 | `react-pnpm-javascript20` | PASS | PASS | PASS | PASS | not_triggered |
| 74 | javascript | 22 | generic | npm 10 | `generic-npm-javascript22` | PASS | PASS | PASS | PASS | not_triggered |
| 75 | javascript | 22 | express | npm 10 | `express-npm-javascript22` | PASS | PASS | PASS | PASS | not_triggered |
| 76 | javascript | 22 | react | pnpm 9 | `react-pnpm-javascript22` | PASS | PASS | PASS | PASS | not_triggered |
| 77 | typescript | 18 | generic | npm 10 | `generic-npm-typescript18` | PASS | PASS | PASS | PASS | not_triggered |
| 78 | typescript | 18 | nestjs | pnpm 9 | `nestjs-pnpm-typescript18` | PASS | PASS | PASS | PASS | not_triggered |
| 79 | typescript | 18 | nextjs | yarn 4 | `nextjs-yarn-typescript18` | PASS | PASS | PASS | PASS | not_triggered |
| 80 | typescript | 20 | generic | npm 10 | `generic-npm-typescript20` | PASS | PASS | PASS | PASS | not_triggered |
| 81 | typescript | 20 | nestjs | pnpm 9 | `nestjs-pnpm-typescript20` | PASS | PASS | PASS | PASS | not_triggered |
| 82 | typescript | 20 | nextjs | yarn 4 | `nextjs-yarn-typescript20` | PASS | PASS | PASS | PASS | not_triggered |
| 83 | typescript | 22 | generic | npm 10 | `generic-npm-typescript22` | PASS | PASS | PASS | PASS | not_triggered |
| 84 | typescript | 22 | nestjs | pnpm 9 | `nestjs-pnpm-typescript22` | PASS | PASS | PASS | PASS | not_triggered |
| 85 | typescript | 22 | nextjs | yarn 4 | `nextjs-yarn-typescript22` | PASS | PASS | PASS | PASS | not_triggered |
| 86 | go | 1.21 | generic | go 1.23 | `generic-go-go1-21` | PASS | PASS | PASS | PASS | not_triggered |
| 87 | go | 1.21 | gin | go 1.23 | `gin-go-go1-21` | PASS | PASS | PASS | PASS | not_triggered |
| 88 | go | 1.21 | fiber | go 1.23 | `fiber-go-go1-21` | PASS | PASS | PASS | PASS | not_triggered |
| 89 | go | 1.22 | generic | go 1.23 | `generic-go-go1-22` | PASS | PASS | PASS | PASS | not_triggered |
| 90 | go | 1.22 | gin | go 1.23 | `gin-go-go1-22` | PASS | PASS | PASS | PASS | not_triggered |
| 91 | go | 1.22 | fiber | go 1.23 | `fiber-go-go1-22` | PASS | PASS | PASS | PASS | not_triggered |
| 92 | go | 1.23 | generic | go 1.23 | `generic-go-go1-23` | PASS | PASS | PASS | PASS | not_triggered |
| 93 | go | 1.23 | gin | go 1.23 | `gin-go-go1-23` | PASS | PASS | PASS | PASS | not_triggered |
| 94 | go | 1.23 | fiber | go 1.23 | `fiber-go-go1-23` | PASS | PASS | PASS | PASS | not_triggered |
| 95 | rust | 1.89 | generic | cargo 1.93 | `generic-cargo-rust1-89` | PASS | PASS | PASS | PASS | not_triggered |
| 96 | rust | 1.89 | actix | cargo 1.93 | `actix-cargo-rust1-89` | PASS | PASS | PASS | PASS | not_triggered |
| 97 | rust | 1.89 | axum | cargo 1.93 | `axum-cargo-rust1-89` | PASS | PASS | PASS | PASS | not_triggered |
| 98 | rust | 1.93 | generic | cargo 1.93 | `generic-cargo-rust1-93` | PASS | PASS | PASS | PASS | not_triggered |
| 99 | rust | 1.93 | actix | cargo 1.93 | `actix-cargo-rust1-93` | PASS | PASS | PASS | PASS | not_triggered |
| 100 | rust | 1.93 | axum | cargo 1.93 | `axum-cargo-rust1-93` | PASS | PASS | PASS | PASS | not_triggered |
| 101 | ruby | 3.2 | generic | bundle 2.5 | `generic-bundle-ruby3-2` | PASS | PASS | PASS | PASS | not_triggered |
| 102 | ruby | 3.2 | rails | bundle 2.5 | `rails-bundle-ruby3-2` | PASS | PASS | PASS | PASS | not_triggered |
| 103 | ruby | 3.3 | generic | bundle 2.5 | `generic-bundle-ruby3-3` | PASS | PASS | PASS | PASS | not_triggered |
| 104 | ruby | 3.3 | rails | bundle 2.5 | `rails-bundle-ruby3-3` | PASS | PASS | PASS | PASS | not_triggered |
| 105 | ruby | 3.4 | generic | bundle 2.5 | `generic-bundle-ruby3-4` | PASS | PASS | PASS | PASS | not_triggered |
| 106 | ruby | 3.4 | rails | bundle 2.5 | `rails-bundle-ruby3-4` | PASS | PASS | PASS | PASS | not_triggered |
| 107 | php | 8.2 | generic | composer 2.8 | `generic-composer-php8-2` | PASS | PASS | PASS | PASS | not_triggered |
| 108 | php | 8.2 | laravel | composer 2.8 | `laravel-composer-php8-2` | PASS | PASS | PASS | PASS | not_triggered |
| 109 | php | 8.3 | generic | composer 2.8 | `generic-composer-php8-3` | PASS | PASS | PASS | PASS | not_triggered |
| 110 | php | 8.3 | laravel | composer 2.8 | `laravel-composer-php8-3` | PASS | PASS | PASS | PASS | not_triggered |
| 111 | php | 8.4 | generic | composer 2.8 | `generic-composer-php8-4` | PASS | PASS | PASS | PASS | not_triggered |
| 112 | php | 8.4 | laravel | composer 2.8 | `laravel-composer-php8-4` | PASS | PASS | PASS | PASS | not_triggered |
| 113 | dotnet | 8.0 | generic | dotnet 9.0 | `generic-dotnet-dotnet8-0` | PASS | PASS | PASS | PASS | not_triggered |
| 114 | dotnet | 8.0 | aspnet | dotnet 9.0 | `aspnet-dotnet-dotnet8-0` | PASS | PASS | PASS | PASS | not_triggered |
| 115 | dotnet | 9.0 | generic | dotnet 9.0 | `generic-dotnet-dotnet9-0` | PASS | PASS | PASS | PASS | not_triggered |
| 116 | dotnet | 9.0 | aspnet | dotnet 9.0 | `aspnet-dotnet-dotnet9-0` | PASS | PASS | PASS | PASS | not_triggered |
| 117 | kotlin | 1.9 | generic | gradle 8.12 | `generic-gradle-kotlin1-9` | PASS | PASS | PASS | PASS | not_triggered |
| 118 | kotlin | 1.9 | spring-boot | gradle 8.12 | `spring-boot-gradle-kotlin1-9` | PASS | PASS | PASS | PASS | not_triggered |
| 119 | kotlin | 2.0 | generic | gradle 8.12 | `generic-gradle-kotlin2-0` | PASS | PASS | PASS | PASS | not_triggered |
| 120 | kotlin | 2.0 | spring-boot | gradle 8.12 | `spring-boot-gradle-kotlin2-0` | PASS | PASS | PASS | PASS | not_triggered |
| 121 | scala | 2.13 | generic | sbt 1.10 | `generic-sbt-scala2-13` | PASS | PASS | PASS | PASS | not_triggered |
| 122 | scala | 2.13 | akka | sbt 1.10 | `akka-sbt-scala2-13` | PASS | PASS | PASS | PASS | not_triggered |
| 123 | scala | 3.3 | generic | sbt 1.10 | `generic-sbt-scala3-3` | PASS | PASS | PASS | PASS | not_triggered |
| 124 | scala | 3.3 | akka | sbt 1.10 | `akka-sbt-scala3-3` | PASS | PASS | PASS | PASS | not_triggered |
| 125 | swift | 5.9 | generic | swiftpm 6.0 | `generic-swiftpm-swift5-9` | PASS | PASS | PASS | PASS | not_triggered |
| 126 | swift | 5.9 | vapor | swiftpm 6.0 | `vapor-swiftpm-swift5-9` | PASS | PASS | PASS | PASS | not_triggered |
| 127 | swift | 6.0 | generic | swiftpm 6.0 | `generic-swiftpm-swift6-0` | PASS | PASS | PASS | PASS | not_triggered |
| 128 | swift | 6.0 | vapor | swiftpm 6.0 | `vapor-swiftpm-swift6-0` | PASS | PASS | PASS | PASS | not_triggered |
| 129 | dart | 3.4 | flutter | pub 3.5 | `flutter-pub-dart3-4` | PASS | PASS | PASS | PASS | not_triggered |
| 130 | dart | 3.4 | shelf | pub 3.5 | `shelf-pub-dart3-4` | PASS | PASS | PASS | PASS | not_triggered |
| 131 | dart | 3.5 | flutter | pub 3.5 | `flutter-pub-dart3-5` | PASS | PASS | PASS | PASS | not_triggered |
| 132 | dart | 3.5 | shelf | pub 3.5 | `shelf-pub-dart3-5` | PASS | PASS | PASS | PASS | not_triggered |
| 133 | c | 17 | generic | make 4.4 | `generic-make-c17` | PASS | PASS | PASS | PASS | not_triggered |
| 134 | c | 17 | cmake | cmake 3.30 | `cmake-cmake-c17` | PASS | PASS | PASS | PASS | not_triggered |
| 135 | c | 23 | generic | make 4.4 | `generic-make-c23` | PASS | PASS | PASS | PASS | not_triggered |
| 136 | c | 23 | cmake | cmake 3.30 | `cmake-cmake-c23` | PASS | PASS | PASS | PASS | not_triggered |
| 137 | cpp | 20 | generic | make 4.4 | `generic-make-cpp20` | PASS | PASS | PASS | PASS | not_triggered |
| 138 | cpp | 20 | cmake | cmake 3.30 | `cmake-cmake-cpp20` | PASS | PASS | PASS | PASS | not_triggered |
| 139 | cpp | 23 | generic | make 4.4 | `generic-make-cpp23` | PASS | PASS | PASS | PASS | not_triggered |
| 140 | cpp | 23 | cmake | cmake 3.30 | `cmake-cmake-cpp23` | PASS | PASS | PASS | PASS | not_triggered |
| 141 | perl | 5.38 | generic | cpanm 1.7047 | `generic-cpanm-perl5-38` | PASS | PASS | PASS | PASS | not_triggered |
| 142 | perl | 5.38 | dancer | cpanm 1.7047 | `dancer-cpanm-perl5-38` | PASS | PASS | PASS | PASS | not_triggered |
| 143 | perl | 5.40 | generic | cpanm 1.7047 | `generic-cpanm-perl5-40` | PASS | PASS | PASS | PASS | not_triggered |
| 144 | perl | 5.40 | dancer | cpanm 1.7047 | `dancer-cpanm-perl5-40` | PASS | PASS | PASS | PASS | not_triggered |
| 145 | r | 4.3 | generic | renv 1.1 | `generic-renv-r4-3` | PASS | PASS | PASS | PASS | not_triggered |
| 146 | r | 4.3 | shiny | renv 1.1 | `shiny-renv-r4-3` | PASS | PASS | PASS | PASS | not_triggered |
| 147 | r | 4.4 | generic | renv 1.1 | `generic-renv-r4-4` | PASS | PASS | PASS | PASS | not_triggered |
| 148 | r | 4.4 | shiny | renv 1.1 | `shiny-renv-r4-4` | PASS | PASS | PASS | PASS | not_triggered |
| 149 | julia | 1.10 | generic | pkg 1.11 | `generic-pkg-julia1-10` | PASS | PASS | PASS | PASS | not_triggered |
| 150 | julia | 1.10 | genie | pkg 1.11 | `genie-pkg-julia1-10` | PASS | PASS | PASS | PASS | not_triggered |
| 151 | julia | 1.11 | generic | pkg 1.11 | `generic-pkg-julia1-11` | PASS | PASS | PASS | PASS | not_triggered |
| 152 | julia | 1.11 | genie | pkg 1.11 | `genie-pkg-julia1-11` | PASS | PASS | PASS | PASS | not_triggered |
| 153 | elixir | 1.16 | generic | mix 1.17 | `generic-mix-elixir1-16` | PASS | PASS | PASS | PASS | not_triggered |
| 154 | elixir | 1.16 | phoenix | mix 1.17 | `phoenix-mix-elixir1-16` | PASS | PASS | PASS | PASS | not_triggered |
| 155 | elixir | 1.17 | generic | mix 1.17 | `generic-mix-elixir1-17` | PASS | PASS | PASS | PASS | not_triggered |
| 156 | elixir | 1.17 | phoenix | mix 1.17 | `phoenix-mix-elixir1-17` | PASS | PASS | PASS | PASS | not_triggered |
| 157 | erlang | 26 | generic | rebar3 3.24 | `generic-rebar3-erlang26` | PASS | PASS | PASS | PASS | not_triggered |
| 158 | erlang | 26 | cowboy | rebar3 3.24 | `cowboy-rebar3-erlang26` | PASS | PASS | PASS | PASS | not_triggered |
| 159 | erlang | 27 | generic | rebar3 3.24 | `generic-rebar3-erlang27` | PASS | PASS | PASS | PASS | not_triggered |
| 160 | erlang | 27 | cowboy | rebar3 3.24 | `cowboy-rebar3-erlang27` | PASS | PASS | PASS | PASS | not_triggered |
| 161 | clojure | 1.11 | generic | deps.edn 1.12 | `generic-deps.edn-clojure1-11` | PASS | PASS | PASS | PASS | not_triggered |
| 162 | clojure | 1.11 | ring | leiningen 2.11 | `ring-leiningen-clojure1-11` | PASS | PASS | PASS | PASS | not_triggered |
| 163 | clojure | 1.12 | generic | deps.edn 1.12 | `generic-deps.edn-clojure1-12` | PASS | PASS | PASS | PASS | not_triggered |
| 164 | clojure | 1.12 | ring | leiningen 2.11 | `ring-leiningen-clojure1-12` | PASS | PASS | PASS | PASS | not_triggered |
| 165 | groovy | 4.0 | generic | gradle 8.12 | `generic-gradle-groovy4-0` | PASS | PASS | PASS | PASS | not_triggered |
| 166 | groovy | 4.0 | grails | gradle 8.12 | `grails-gradle-groovy4-0` | PASS | PASS | PASS | PASS | not_triggered |
| 167 | groovy | 5.0 | generic | gradle 8.12 | `generic-gradle-groovy5-0` | PASS | PASS | PASS | PASS | not_triggered |
| 168 | groovy | 5.0 | grails | gradle 8.12 | `grails-gradle-groovy5-0` | PASS | PASS | PASS | PASS | not_triggered |
| 169 | lua | 5.4 | generic | luarocks 3.11 | `generic-luarocks-lua5-4` | PASS | PASS | PASS | PASS | not_triggered |
| 170 | lua | 5.4 | lapis | luarocks 3.11 | `lapis-luarocks-lua5-4` | PASS | PASS | PASS | PASS | not_triggered |
| 171 | lua | luajit-2.1 | generic | luarocks 3.11 | `generic-luarocks-lualuajit-2-1` | PASS | PASS | PASS | PASS | not_triggered |
| 172 | lua | luajit-2.1 | lapis | luarocks 3.11 | `lapis-luarocks-lualuajit-2-1` | PASS | PASS | PASS | PASS | not_triggered |
| 173 | haskell | 9.6 | generic | stack 2.15 | `generic-stack-haskell9-6` | PASS | PASS | PASS | PASS | not_triggered |
| 174 | haskell | 9.6 | servant | cabal 3.12 | `servant-cabal-haskell9-6` | PASS | PASS | PASS | PASS | not_triggered |
| 175 | haskell | 9.8 | generic | stack 2.15 | `generic-stack-haskell9-8` | PASS | PASS | PASS | PASS | not_triggered |
| 176 | haskell | 9.8 | servant | cabal 3.12 | `servant-cabal-haskell9-8` | PASS | PASS | PASS | PASS | not_triggered |
| 177 | nim | 2.0 | generic | nimble 0.16 | `generic-nimble-nim2-0` | PASS | PASS | PASS | PASS | not_triggered |
| 178 | nim | 2.0 | jester | nimble 0.16 | `jester-nimble-nim2-0` | PASS | PASS | PASS | PASS | not_triggered |
| 179 | nim | 2.2 | generic | nimble 0.16 | `generic-nimble-nim2-2` | PASS | PASS | PASS | PASS | not_triggered |
| 180 | nim | 2.2 | jester | nimble 0.16 | `jester-nimble-nim2-2` | PASS | PASS | PASS | PASS | not_triggered |
| 181 | zig | 0.13 | generic | zig 0.14 | `generic-zig-zig0-13` | PASS | PASS | PASS | PASS | not_triggered |
| 182 | zig | 0.13 | httpz | zig 0.14 | `httpz-zig-zig0-13` | PASS | PASS | PASS | PASS | not_triggered |
| 183 | zig | 0.14 | generic | zig 0.14 | `generic-zig-zig0-14` | PASS | PASS | PASS | PASS | not_triggered |
| 184 | zig | 0.14 | httpz | zig 0.14 | `httpz-zig-zig0-14` | PASS | PASS | PASS | PASS | not_triggered |
| 185 | crystal | 1.12 | generic | shards 0.17 | `generic-shards-crystal1-12` | PASS | PASS | PASS | PASS | not_triggered |
| 186 | crystal | 1.12 | kemal | shards 0.17 | `kemal-shards-crystal1-12` | PASS | PASS | PASS | PASS | not_triggered |
| 187 | crystal | 1.13 | generic | shards 0.17 | `generic-shards-crystal1-13` | PASS | PASS | PASS | PASS | not_triggered |
| 188 | crystal | 1.13 | kemal | shards 0.17 | `kemal-shards-crystal1-13` | PASS | PASS | PASS | PASS | not_triggered |
| 189 | ocaml | 5.1 | generic | dune 3.16 | `generic-dune-ocaml5-1` | PASS | PASS | PASS | PASS | not_triggered |
| 190 | ocaml | 5.1 | dream | dune 3.16 | `dream-dune-ocaml5-1` | PASS | PASS | PASS | PASS | not_triggered |
| 191 | ocaml | 5.2 | generic | dune 3.16 | `generic-dune-ocaml5-2` | PASS | PASS | PASS | PASS | not_triggered |
| 192 | ocaml | 5.2 | dream | dune 3.16 | `dream-dune-ocaml5-2` | PASS | PASS | PASS | PASS | not_triggered |
| 193 | fsharp | 8.0 | generic | dotnet 9.0 | `generic-dotnet-fsharp8-0` | PASS | PASS | PASS | PASS | not_triggered |
| 194 | fsharp | 8.0 | giraffe | dotnet 9.0 | `giraffe-dotnet-fsharp8-0` | PASS | PASS | PASS | PASS | not_triggered |
| 195 | fsharp | 9.0 | generic | dotnet 9.0 | `generic-dotnet-fsharp9-0` | PASS | PASS | PASS | PASS | not_triggered |
| 196 | fsharp | 9.0 | giraffe | dotnet 9.0 | `giraffe-dotnet-fsharp9-0` | PASS | PASS | PASS | PASS | not_triggered |
| 197 | bash | 5.1 | generic | make 4.4 | `generic-make-bash5-1` | PASS | PASS | PASS | PASS | not_triggered |
| 198 | bash | 5.1 | bats | bats 1.11 | `bats-bats-bash5-1` | PASS | PASS | PASS | PASS | not_triggered |
| 199 | bash | 5.2 | generic | make 4.4 | `generic-make-bash5-2` | PASS | PASS | PASS | PASS | not_triggered |
| 200 | bash | 5.2 | bats | bats 1.11 | `bats-bats-bash5-2` | PASS | PASS | PASS | PASS | not_triggered |
