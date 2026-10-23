<#--
  Choix d'un nouveau mot de passe : à la première connexion (mot de passe provisoire donné par
  l'administrateur), ou quand la personne le demande depuis « Mon compte » (action demandée par
  l'outil : bouton « Annuler » en plus).
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('password','password-confirm'); section>
    <#if section = "header">
        ${msg("updatePasswordTitle")}
    <#elseif section = "form">
        <form id="kc-passwd-update-form" class="form" onsubmit="login.disabled = true; return true;"
              action="${url.loginAction}" method="post">
            <div class="field">
                <label for="password-new">${msg("passwordNew")}</label>
                <input type="password" id="password-new" name="password-new" autofocus autocomplete="new-password"
                       required aria-invalid="<#if messagesPerField.existsError('password','password-confirm')>true</#if>"/>
                <#if messagesPerField.existsError('password')>
                    <span class="field-error" aria-live="polite">${kcSanitize(messagesPerField.get('password'))?no_esc}</span>
                </#if>
                <span class="field-help">${msg("passwordRule")}</span>
            </div>
            <div class="field">
                <label for="password-confirm">${msg("passwordConfirm")}</label>
                <input type="password" id="password-confirm" name="password-confirm" autocomplete="new-password"
                       required aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"/>
                <#if messagesPerField.existsError('password-confirm')>
                    <span class="field-error" aria-live="polite">${kcSanitize(messagesPerField.get('password-confirm'))?no_esc}</span>
                </#if>
            </div>
            <label class="checkbox-field">
                <input type="checkbox" id="logout-sessions" name="logout-sessions" value="on" checked>
                ${msg("logoutOtherSessions")}
            </label>
            <#-- « Enregistrer » d'abord : la touche Entrée envoie le PREMIER bouton du formulaire. Affichés
                 dans l'autre sens (Annuler à gauche) par la feuille de style. -->
            <div class="form-buttons">
                <button class="button-primary" name="login" type="submit">${msg("doSubmit")}</button>
                <#if isAppInitiatedAction??>
                    <button class="button-secondary" type="submit" name="cancel-aia" value="true" formnovalidate>${msg("doCancel")}</button>
                </#if>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
