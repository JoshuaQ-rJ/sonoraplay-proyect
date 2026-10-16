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

**Publicación:** la configuración incluye la URL base prevista para GitHub Pages y existe un workflow de Docusaurus en `develop`, pero una compilación correcta no significa que el portal esté publicado. Joshua debe integrar el workflow en `main` y un administrador debe configurar **Settings → Pages → Build and deployment → GitHub Actions**. No se modifica `main` ni se activa Pages desde esta guía.

## English

This portal reuses the existing `docs/` directory and **does not alter** the SonoraPlay application.

1. Install Node.js 20 or newer.
2. Run `npm install`.
3. Run `npm run docs:start` to preview the portal locally.
4. Run `npm run docs:build` before opening a PR.
5. Add new Markdown deliverables under `docs/`, referencing their Jira story and verified evidence. Provide equivalent English and Spanish content.

The locale selector is configured, but **historical technical documents have not been fully translated**. Spanish is the source language; `Overview · English` provides an English overview. Do not claim the remaining pages are translated.

**Publishing:** the GitHub Pages base URL is preconfigured and a Docusaurus workflow exists on `develop`, but a successful build does not mean the portal is publicly deployed. Joshua must integrate the workflow into `main`, and an administrator must configure **Settings → Pages → Build and deployment → GitHub Actions**. This guide does not modify `main` or enable Pages.


## Lista de verificación de entrega / Delivery checklist

### Español

- [ ] Confirmar que el workflow de Docusaurus y la documentación aprobada están en `main` (responsable: Joshua).
- [ ] Confirmar que GitHub Pages utiliza **GitHub Actions** como fuente (requiere administrador).
- [ ] Comprobar un despliegue **build + deploy** exitoso desde `main`; una compilación de PR no basta.
- [ ] Abrir `https://joshuaq-rj.github.io/sonoraplay-proyect/` en una ventana privada y comprobar que es accesible sin iniciar sesión.
- [ ] Revisar portada, navegación lateral, imagen de arquitectura, enlaces internos y páginas de datos, servicios y ADR.
- [ ] Comprobar el selector de idiomas sin afirmar que todos los documentos históricos están traducidos.
- [ ] Guardar capturas de la URL pública y del workflow de despliegue, con fecha y commit.
- [ ] Marcar los componentes AWS como **diseño/propuesta** hasta disponer de evidencias reales de despliegue.

**Diagnóstico:** si la URL devuelve 404, revisar primero que Pages esté habilitado, que el workflow exista en `main` y que `baseUrl` sea `/sonoraplay-proyect/`. Si el sitio abre pero faltan páginas, revisar los enlaces relativos y el registro de compilación. No publicar secretos ni capturas con credenciales.

### English

- [ ] Confirm that the Docusaurus workflow and approved documentation have reached `main` (owner: Joshua).
- [ ] Confirm GitHub Pages uses **GitHub Actions** as its source (administrator required).
- [ ] Verify a successful **build + deploy** run from `main`; a PR build alone is insufficient.
- [ ] Open `https://joshuaq-rj.github.io/sonoraplay-proyect/` in a private window and verify access without signing in.
- [ ] Check the homepage, sidebar, architecture image, internal links, data, services, and ADR pages.
- [ ] Test the locale selector without claiming that all historical documents are translated.
- [ ] Save dated screenshots of the public URL and deployment workflow, including the commit identifier.
- [ ] Label AWS components as **design/proposal** until real deployment evidence is available.

**Troubleshooting:** for a 404, first check that Pages is enabled, the workflow exists on `main`, and `baseUrl` is `/sonoraplay-proyect/`. If the site loads but pages are missing, check relative links and build logs. Never publish secrets or credential-bearing screenshots.
