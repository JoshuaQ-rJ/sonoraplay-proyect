---
id: docusaurus-guia
title: Guía de Docusaurus · Docusaurus guide
sidebar_position: 3
---

# Documentación / Documentation

## Español

Este portal reutiliza la carpeta `docs/` existente y **no cambia** el funcionamiento de SonoraPlay.

1. Instala Node.js 20 o superior.
2. Ejecuta `npm install`.
3. Ejecuta `npm run docs:start` para abrir el portal local.
4. Ejecuta `npm run docs:build` antes de abrir un PR.
5. Escribe las nuevas entregas en Markdown bajo `docs/`, con su historia Jira y evidencias verificables. Incluye el contenido equivalente en inglés y español.

El selector de idioma está preparado, pero **los documentos históricos aún no tienen traducción completa**. El contenido en español es el original; la página `Overview · English` es un resumen equivalente de la introducción. No se debe presentar el resto como traducido.

**Publicación:** la configuración incluye la URL base prevista para GitHub Pages, pero este PR no activa Pages ni realiza despliegues. Joshua debe aprobar el destino y las políticas de publicación antes de configurar el workflow.

## English

This portal reuses the existing `docs/` directory and **does not alter** the SonoraPlay application.

1. Install Node.js 20 or newer.
2. Run `npm install`.
3. Run `npm run docs:start` to preview the portal locally.
4. Run `npm run docs:build` before opening a PR.
5. Add new Markdown deliverables under `docs/`, referencing their Jira story and verified evidence. Provide equivalent English and Spanish content.

The locale selector is configured, but **historical technical documents have not been fully translated**. Spanish is the source language; `Overview · English` provides an English overview. Do not claim the remaining pages are translated.

**Publishing:** the GitHub Pages base URL is preconfigured, but this PR does not enable Pages or deploy anything. Joshua must approve the publishing destination and workflow first.
