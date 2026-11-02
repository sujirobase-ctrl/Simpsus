# BUIDL 2.0.0 — GUI Windows + APK Android

Este repositório guarda o código-fonte dos dois aplicativos promovidos da linha
1.4.5 para 2.0.0: a interface desktop “Nova interface” e o app Android nativo.
As releases contêm somente o executável Windows e o APK Android.

## O que é gerado

- `BUIDL-2.0.0.exe`: GUI desktop em Python/WebView2, baseada em `desktop.py` e
  `desktop_ui/`.
- `BUIDL-2.0.0-Android.apk`: interface Android em Java Views com o mesmo núcleo
  Python. O WebView é usado somente para captura de cookies dentro do app.

O APK do Actions é uma compilação debug para instalação manual, não uma versão
assinada para publicação na Play Store.

## Baixar

Acesse [Releases](https://github.com/sujirobase-ctrl/Simpsus/releases). A tag
`v2.0.0` gera os dois artefatos pelo GitHub Actions após os testes e builds
passarem.

## Compilar no Windows

Requer Python 3.14, Node.js 24, dependências de `requirements.txt` e o runtime
Microsoft Edge WebView2. Na raiz do repositório:

```powershell
python -m pip install -r requirements.txt
pyinstaller --clean --noconfirm buidl-desktop.spec
```

O executável sai em `dist/BUIDL-2.0.0.exe`.

## Compilar o APK

Requer JDK 21, Android SDK 36/build-tools 36.0.0 e Python 3.14 para Chaquopy.
No Windows, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File android\build.ps1
```

O APK sai em `android/app/build/outputs/apk/debug/app-debug.apk`.

## Privacidade dos dados de build

Não adicione cookies, sessões, downloads, logs pessoais, chaves ou arquivos de
configuração locais. O `.gitignore` exclui esses dados e as saídas de build/QA.
O workflow cria a release somente com os dois artefatos listados acima.
