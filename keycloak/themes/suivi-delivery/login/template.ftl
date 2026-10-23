<#--
  Cadre commun des pages de connexion : la barre du haut et la carte de connexion de l'outil
  (frontend/app/layout.tsx et l'ancienne page /connexion/autoriser), au lieu de celles de Keycloak.

  Repris du « template.ftl » du thème « base » de Keycloak (même macro, mêmes sections : header,
  form, info…), en gardant ses scripts utiles (connexion ouverte dans un autre onglet, liens
  cliquables une seule fois) et en retirant ce qui ne sert pas ici (choix de la langue,
  fournisseurs d'identité externes).
-->
<#import "footer.ftl" as loginFooter>
<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <#-- Le thème choisi dans l'outil (« Mon compte » → Apparence), recopié par l'interface dans le
         cookie sd_theme_auth (frontend/proxy.ts) : posé avant l'affichage, sans clignotement. -->
    <script>
        try {
            var choice = document.cookie.match(/(?:^|; )sd_theme_auth=(LIGHT|DARK)(?:;|$)/);
            if (choice) document.documentElement.dataset.theme = choice[1] === "LIGHT" ? "light" : "dark";
        } catch (e) {}
    </script>
    <title>Suivi de la delivery<#if properties.instanceName?has_content> · ${properties.instanceName}</#if></title>
    <#-- Les couleurs de l'outil, écrites dans la page (et non en fichier à part) : un navigateur ne
         peut pas garder une ancienne version en cache quand le thème change (l'adresse des
         fichiers de Keycloak, elle, ne change pas). -->
    <style>
<#include "resources/css/suivi-delivery.css" parse=false>
    </style>
    <script type="importmap">
        {
            "imports": {
                "rfc4648": "${url.resourcesCommonPath}/vendor/rfc4648/rfc4648.js"
            }
        }
    </script>
    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="module">
        <#outputformat "JavaScript">
        import { startSessionPolling } from ${(url.resourcesPath + "/js/authChecker.js")?c};

        startSessionPolling(
            ${url.ssoLoginInOtherTabsUrl?c}
        );
        </#outputformat>
    </script>
    <script type="module">
        document.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-once-link]");
            if (!link) {
                return;
            }
            if (link.getAttribute("aria-disabled") === "true") {
                event.preventDefault();
                return;
            }
            link.setAttribute("role", "link");
            link.setAttribute("aria-disabled", "true");
        });
    </script>
    <#if authenticationSession??>
        <script type="module">
            <#outputformat "JavaScript">
            import { checkAuthSession } from ${(url.resourcesPath + "/js/authChecker.js")?c};

            checkAuthSession(
                ${authenticationSession.authSessionIdHash?c}
            );
            </#outputformat>
        </script>
    </#if>
</head>

<body data-page-id="login-${pageId}">
<header class="top-bar">
    <#if properties.instanceName?has_content>
        <div class="instance-banner<#if !properties.instanceColor?has_content && properties.instanceName?lower_case?matches('prod|production')> prod</#if>"
             <#if properties.instanceColor?has_content && properties.instanceColor?matches('#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30}')>style="background: ${properties.instanceColor}"</#if>>
            Instance : <strong>${properties.instanceName}</strong>
        </div>
    </#if>
    <div class="top-bar-content">
        <div class="brand"><span class="logo" aria-hidden="true">◆</span> Suivi de la delivery</div>
    </div>
</header>

<main class="page">
    <div class="login">
        <section class="login-card ${bodyClass}">
            <header class="login-header">
                <div class="login-logo" aria-hidden="true">◆</div>
                <h1>Suivi de la delivery</h1>
                <p id="kc-page-title"><#nested "header"></p>
            </header>

            <#if auth?has_content && auth.showUsername() && !auth.showResetCredentials()>
                <#nested "show-username">
                <p class="login-identity">
                    ${auth.attemptedUsername}
                    · <a id="reset-login" href="${url.loginRestartFlowUrl}">${msg("restartLoginTooltip")}</a>
                </p>
            </#if>

            <#-- Les actions demandées par l'outil (changer de mot de passe) n'affichent pas l'avertissement
                 « vous devez changer de mot de passe » : la personne vient de le demander. -->
            <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                <div class="<#if message.type = 'error'>form-alert<#else>banner ${message.type}</#if>" role="alert">
                    ${kcSanitize(message.summary)?no_esc}
                </div>
            </#if>

            <#nested "form">

            <#if auth?has_content && auth.showTryAnotherWayLink()>
                <form id="kc-select-try-another-way-form" action="${url.loginAction}" method="post">
                    <input type="hidden" name="tryAnotherWay" value="on"/>
                    <button type="submit" class="link">${msg("doTryAnotherWay")}</button>
                </form>
            </#if>

            <#if displayInfo>
                <div id="kc-info"><#nested "info"></div>
            </#if>

            <@loginFooter.content/>
        </section>
    </div>
</main>
</body>
</html>
</#macro>
