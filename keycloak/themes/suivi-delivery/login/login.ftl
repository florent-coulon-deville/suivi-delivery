<#--
  La page de connexion : identifiant et mot de passe, à l'identique de l'ancienne page de l'outil
  (frontend/app/login/autoriser). Pas d'inscription ni de « mot de passe oublié » : c'est
  l'administrateur de l'outil qui crée les comptes (écran Comptes).
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=true; section>
    <#if section = "header">
        ${msg("loginAccountTitle")}
    <#elseif section = "form">
        <#if realm.password>
            <form id="kc-form-login" class="form" onsubmit="login.disabled = true; return true;"
                  action="${url.loginAction}" method="post">
                <#if messagesPerField.existsError('username','password')>
                    <div class="form-alert" role="alert" aria-live="polite">
                        <strong>Refusé :</strong>
                        ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
                    </div>
                </#if>
                <#if !usernameHidden??>
                    <div class="field">
                        <label for="username">${msg("username")}</label>
                        <input id="username" name="username" value="${(login.username!'')}" type="text"
                               autofocus autocomplete="username" required dir="ltr"
                               aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"/>
                    </div>
                </#if>
                <div class="field">
                    <label for="password">${msg("password")}</label>
                    <input id="password" name="password" type="password" autocomplete="current-password" required
                           <#if usernameHidden??>autofocus</#if>
                           aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"/>
                </div>
                <input type="hidden" id="id-hidden-input" name="credentialId"
                       <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                <button class="button-primary button-large" name="login" id="kc-login" type="submit">
                    ${msg("doLogIn")}
                </button>
            </form>
        </#if>
    <#elseif section = "info">
        <p class="login-help">${msg("loginHelp")?no_esc}</p>
    </#if>
</@layout.registrationLayout>
