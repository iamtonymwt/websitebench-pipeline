import { LitElement, html, css } from './lit-all.min.js';

class MonopriceFooter extends LitElement {
  static properties = {
    WWWDomain: { type: String, reflect: true },
    serverSetting: { type: String, reflect: true },
    cartData: { type: Object, attribute: 'cart-data' },
    MPIRequest: { type: Object, attribute: 'mpi-request' },
    SCREEN_ID: { type: String, attribute: 'screen-id' },
    isB2B: { type: Boolean, reflect: true },
    assemblyVersion: { type: String, reflect: true },
    showSuccessMessage: { type: Boolean },
    errorMessage: { type: String },
    isSubmitting: { type: Boolean },

    // Internal state: whether a light-DOM a11y link is slotted
    _hasA11ySlot: { state: true },
  };

  constructor() {
    super();
    this.WWWDomain = 'https://www.monoprice.com';
    this.serverSetting = '';
    this.showSuccessMessage = false;
    this.isSubmitting = false;
    this.errorMessage = '';
    this.cartData = null;
    this.MPIRequest = null;
    this.SCREEN_ID = '';
    this.showSuccessMessage = false;
    this.errorMessage = '';
    this.isSubmitting = false;

    this._hasA11ySlot = false;
    this._a11yEl = null; // holds the slotted element ref, if any
    this._a11yTimer = null;
  }

  connectedCallback() {
    super.connectedCallback();
    this._waitForA11y();

    // If the slot is already populated when connected, wire it up after first render.
    this.updateComplete?.then(() => this._wireA11yLink());
  }

  disconnectedCallback() {
    super.disconnectedCallback?.();
    if (this._a11yTimer) clearTimeout(this._a11yTimer);
    if (this._a11yEl) this._a11yEl.removeEventListener('click', this.openMenu);
  }

  _waitForA11y(timeoutMs = 10000) {
    const t0 = Date.now();
    const tick = () => {
      if (window.interdeal?.a11y?.openMenu) {
        this.classList.add('has-a11y');
        return;
      }
      if (Date.now() - t0 < timeoutMs) {
        this._a11yTimer = setTimeout(tick, 200);
      } else {
        console.warn('A11y widget not found within timeout.');
      }
    };
    tick();
  }

  static get icons() {
    return {
      facebook: html`<svg viewBox="0 0 320 512"><path d="M279.14 288l14.22-92.66h-88.91v-60.13c0-25.35 12.42-50.06 52.24-50.06h40.42V6.26S260.43 0 225.36 0c-73.22 0-121.08 44.38-121.08 124.72v70.62H22.89V288h81.39v224h100.17V288z"/></svg>`,
      x: html`<svg viewBox="0 0 512 512"><path d="M389.2 48h70.6L305.6 224.2 487 464H345L233.7 318.6 106.5 464H35.8L200.7 275.5 26.8 48H172.4L272.9 180.9 389.2 48zM364.4 421.8h39.1L151.1 88h-42L364.4 421.8z"/></svg>`,
      youtube: html`<svg viewBox="0 0 576 512"><path d="M549.655 124.083c-6.281-23.65-24.787-42.276-48.284-48.597C458.781 64 288 64 288 64S117.22 64 74.629 75.486c-23.497 6.322-42.003 24.947-48.284 48.597-11.412 42.867-11.412 132.305-11.412 132.305s0 89.438 11.412 132.305c6.281 23.65 24.787 41.5 48.284 47.821C117.22 448 288 448 288 448s170.78 0 213.371-11.486c23.497-6.321 42.003-24.171 48.284-47.821 11.412-42.867 11.412-132.305 11.412-132.305s0-89.438-11.412-132.305zm-317.51 213.508V175.185l142.739 81.205-142.739 81.201z"/></svg>`,
      instagram: html`<svg viewBox="0 0 448 512"><path d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg>`,
      linkedin: html`<svg viewBox="0 0 448 512"><path d="M416 32H31.9C14.3 32 0 46.5 0 64.3v383.4C0 465.5 14.3 480 31.9 480H416c17.6 0 32-14.5 32-32.3V64.3c0-17.8-14.4-32.3-32-32.3zM135.4 416H69V202.2h66.5V416zm-33.2-243c-21.3 0-38.5-17.3-38.5-38.5S80.9 96 102.2 96c21.2 0 38.5 17.3 38.5 38.5 0 21.3-17.2 38.5-38.5 38.5zm282.1 243h-66.4V312c0-24.8-.5-56.7-34.5-56.7-34.6 0-39.9 27-39.9 54.9V416h-66.4V202.2h63.7v29.2h.9c8.9-16.8 30.6-34.5 62.9-34.5 67.2 0 79.7 44.3 79.7 101.9V416z"/></svg>`,
      arrow: html`<svg viewBox="0 0 448 512"><path d="M438.6 278.6c12.5-12.5 12.5-32.8 0-45.3l-160-160c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L338.8 224 32 224c-17.7 0-32 14.3-32 32s14.3 32 32 32l306.7 0L233.4 393.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l160-160z"/></svg>`
    };
  }

  getCreateQuoteUrl() {
    if (this.MPIRequest?.CartItemSummaries?.length === 0) {
      return `${this.WWWDomain}/cart/index?emptycart=true`;
    }

    if (this.SCREEN_ID?.toLowerCase() === 'cart' || this.SCREEN_ID?.toLowerCase() === 'quote') {
      if (this.SCREEN_ID?.toLowerCase() === 'cart' &&
        this.cartData?.quoteCart?.Quote) {
        return `${this.WWWDomain}/quote/index?cartid=${this.MPIRequest.CartId}&emailaddress=${this.cartData.quoteCart.Quote.email_address}`;
      }
      return `${this.WWWDomain}/quote/index?cartid=${this.MPIRequest.CartId}`;
    }

    // Default case
    return `${this.WWWDomain}/cart`;
  }

  updated(changedProperties) {
    super.updated(changedProperties);
  }

  async handleEmailSubmit(e) {
    e.preventDefault();
    const emailInput = this.shadowRoot.querySelector('input[type="email"]');
    const email = emailInput.value.trim();

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      this.errorMessage = 'Please enter a valid email address';
      this.showSuccessMessage = false;
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = '';

    try {
      const response = await fetch('/Home/EmailSubcription?email_address=' + email, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email_address: email })
      });

      if (!response.ok) {
        throw new Error('Subscription failed');
      }

      emailInput.value = '';
      this.showSuccessMessage = true;

      if (typeof linkTrack === 'function') {
        linkTrack('emailSubscription');
      }

      setTimeout(() => {
        this.showSuccessMessage = false;
      }, 5000);

    } catch (error) {
      console.error('Subscription error:', error);
      this.errorMessage = 'Something went wrong. Please try again.';
    } finally {
      this.isSubmitting = false;
    }
  }

  openMenu = (e) => {
    e?.preventDefault?.();
    const api = window.interdeal?.a11y;
    if (api?.openMenu) {
      api.openMenu();
    } else {
      console.warn('A11y widget not ready yet.');
    }
  };

  openCookieSettings = (e) => {
    e?.preventDefault?.();
    try {
      if (window.OneTrust?.ToggleInfoDisplay) {
        window.OneTrust.ToggleInfoDisplay();
        return;
      }
      if (window.Optanon?.ToggleInfoDisplay) {
        window.Optanon.ToggleInfoDisplay();
        return;
      }
      window.dispatchEvent(new Event('onetrust-pc-open'));
    } catch (err) {
      console.warn('Unable to open OneTrust preferences center:', err);
    }
  };

  _wireA11yLink = () => {
    const slot = this.shadowRoot?.querySelector('slot[name="a11y-link"]');
    if (!slot) return;

    const assigned = slot.assignedElements({ flatten: true });
    const el = assigned[0];

    this._hasA11ySlot = !!el;

    if (this._a11yEl && this._a11yEl !== el) {
      this._a11yEl.removeEventListener('click', this.openMenu);
      this._a11yEl = null;
    }

    if (el) {
      this._a11yEl = el;
      if (!el.hasAttribute('role')) el.setAttribute('role', 'button');
      el.setAttribute('data-a11y-link', '');
      el.removeEventListener('click', this.openMenu);
      el.addEventListener('click', this.openMenu);
    }
  };

  static styles = css`
    :host {
      display: block;
      font-family: 'Hind', sans-serif;
      background-color: #212121;
      color: #FFFFFF;
      padding: 40px 20px;
    }

    #logo {
      width: 350px;
      margin-bottom: 60px;
      margin-left: 17%;
    }

    .footer-container {
      max-width: 65%;
      margin: 0 auto;
      display: flex;
      flex-direction: row;
      justify-content: space-around;
    }
    #links {
      display: grid;
      grid-template-columns: repeat(3, 1fr) 2fr;
      gap: 24px;
    }

    .footer-links {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .footer-links a {
      color: #FFFFFF;
      text-decoration: none;
      font-size: 14px;
      line-height: 1.5;
      transition: 0.16s color ease-in-out;
    }

    .footer-links a:hover {
      text-decoration: underline;
      color: #00a7bb;
    }

    ::slotted([slot="a11y-link"]) {
      color: #FFFFFF;
      text-decoration: none;
      font-size: 14px;
      line-height: 1.5;
      transition: 0.16s color ease-in-out;
      cursor: pointer !important;
    }
    ::slotted([slot="a11y-link"]:hover) {
      text-decoration: underline;
      color: #00a7bb;
    }

    .email-signup {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    h2 {
      font-size: 16px;
      font-weight: bold;
      margin: 0 0 8px 0;
      text-transform: uppercase;
    }

    .email-input-container {
      position: relative;
      max-width: 300px;
    }

    input[type="email"] {
      width: 100%;
      padding: 12px;
      border: unset;
      border-bottom: 1px solid #fff;
      background: transparent;
      color: #FFFFFF;
      font-size: 14px;
    }

    input[type="email"]::placeholder {
      color: #FFFFFF;
      opacity: 0.8;
    }

    .submit-button {
      position: absolute;
      right: -20px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      color: #FFFFFF;
      cursor: pointer;
    }
    .submit-button svg {
      fill: #fff;
      width: 16px;
      height: 16px;
    }

    .email-message {
      font-size: 14px;
      margin-top: 10px;
      padding: 10px;
      border-radius: 4px;
    }

    .success-message {
      background-color: rgba(255, 255, 255, 0.1);
      color: #fff;
    }

    .error-message {
      background-color: rgba(255, 0, 0, 0.1);
      color: #ff6b6b;
    }

    .email-input-container.submitting input,
    .email-input-container.submitting button {
      opacity: 0.7;
      pointer-events: none;
    }

    .hidden {
      display: none;
    }

    .terms-text {
      font-size: 12px;
      color: #FFFFFF;
      opacity: 0.8;
      max-width: 300px;
    }

    .terms-text a {
      color: #FFFFFF;
      text-decoration: underline;
    }

    .social-links {
      display: flex;
      gap: 20px;
    }

    .social-links a {
      color: #FFFFFF;
      font-size: 20px;
    }
    .social-links svg {
      width: 24px;
      height: 24px;
      fill: #fff;
      transition: 0.16s all ease-in-out;
    }
    .social-links svg:hover {
      fill: #00a7bb;
    }

    .footer-bottom {
      margin-top: 40px;
      padding: 20px 160px 0;
      border-top: 1px solid rgba(255, 255, 255, 0.2);
      display: flex;
      justify-content: space-around;
      align-items: center;
      font-size: 12px;
    }

    .footer-bottom-links {
      display: flex;
      gap: 20px;
      justify-content: center;
      align-items: center;
    }

    .footer-bottom-links a {
      color: #FFFFFF;
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .footer-bottom-links a:hover {
      text-decoration: underline;
    }

    button {
      background: transparent;
      border: 1px solid #fff;
      padding: 1rem 0.7rem;
      color: #fff;
      cursor: pointer;
    }

    #accessibility {
      cursor: pointer !important;
    }

    ::slotted([slot="a11y-link"]) {
      color: #FFFFFF !important;
      text-decoration: none !important;
      font-size: 14px !important;
      line-height: 1.5 !important;
      transition: 0.16s color ease-in-out;
      cursor: pointer !important;

      display: inline !important;
      visibility: visible !important;
      opacity: 1 !important;
      pointer-events: auto !important;
    }
    ::slotted([slot="a11y-link"]:hover) {
      text-decoration: underline !important;
      color: #00a7bb !important;
    }

    @media (max-width: 1000px) {
      .footer-bottom {
        padding: 20px !important;
      }
    }

    @media (max-width: 768px) {
      .footer-container {
        grid-template-columns: 1fr;
        gap: 30px;
        display: grid;
        max-width: unset;
      }
      #links {
        display: grid;
        grid-template-columns: 1fr;
      }
      #logo {
        display: flex;
        margin: 30px auto 0;
      }
      .footer-links {
        align-items: center;
      }
      .footer-links a {
        text-align: center;
      }
      .footer-links h2 {
        margin: 42px 0 0 0;
      }
      .email-signup {
        border-top: 1px solid rgba(255, 255, 255, 0.2);
        margin-top: 16px;
        padding-top: 32px;
        align-items: center;
      }
      .footer-bottom {
        flex-direction: column;
        gap: 20px;
        text-align: center;
      }

      .footer-bottom-links {
        flex-direction: column;
        gap: 10px;
      }
    }
  `;

  renderEmailSignup() {
    return html`
      <div class="email-signup">
        <h2>Sign up for email deals</h2>

        <form @submit=${this.handleEmailSubmit}>
          <div class="email-input-container ${this.isSubmitting ? 'submitting' : ''}">
            <input
              type="email"
              id="footer-email-input"
              placeholder="Email Address"
              aria-label="Email Address"
              ?disabled=${this.isSubmitting}
            >
            <button
              class="submit-button"
              id="footer-email-register"
              aria-label="Submit"
              ?disabled=${this.isSubmitting}
              type="submit"
            >
              ${this.constructor.icons.arrow}
            </button>
          </div>

          ${this.showSuccessMessage ? html`
            <div class="email-message success-message">
              Thanks for signing up!
            </div>
          ` : ''}

          ${this.errorMessage ? html`
            <div class="email-message error-message">
              ${this.errorMessage}
            </div>
          ` : ''}

          <p class="terms-text">
            By providing your email address and clicking Submit, you agree to our 
            <a href="${this.WWWDomain}/terms-of-use" title="Terms of Use" aria-label="email-terms-of-use">Terms of Use</a> and
            <a href="${this.WWWDomain}/privacy" title="Privacy Policy" aria-label="email-privacy-policy">Privacy Policy</a>
          </p>
        </form>

        <h2>Connect with us</h2>
        <div class="social-links">
          <a href="https://www.facebook.com/Monopricecom" target="_blank" title="Facebook" aria-label="Facebook">
            ${this.constructor.icons.facebook}
          </a>
          <a href="https://twitter.com/monoprice" target="_blank" title="X" aria-label="X">
            ${this.constructor.icons.x}
          </a>
          <a href="https://www.youtube.com/Monopricecom" target="_blank" title="YouTube" aria-label="YouTube">
            ${this.constructor.icons.youtube}
          </a>
          <a href="https://instagram.com/monoprice" target="_blank" title="Instagram" aria-label="Instagram">
            ${this.constructor.icons.instagram}
          </a>
          <a href="https://linkedin.com/company/monoprice" target="_blank" title="LinkedIn" aria-label="LinkedIn">
            ${this.constructor.icons.linkedin}
          </a>
        </div>
      </div>
    `;
  }

  renderBusinessLinks() {
    return html`
      <h2>BUSINESS</h2>
      <a href="${this.getCreateQuoteUrl()}" title="Create Quote" aria-label="create-quote">Create Quote</a>
      <a href="${this.WWWDomain}/quote/retrieve" title="Retrieve Quote" aria-label="retrieve-quote">Retrieve Quote</a>
      <a href="${this.WWWDomain}/pages/Reseller_Tax_Exempt_Samples" title="Reseller/Tax Exemption Samples" aria-label="reseller-tax-exemption-samples">Reseller/Tax Exemption Samples</a>
      <a href="${this.WWWDomain}/pages/MPCase_Studies" title="Case Studies" aria-label="case-studies">Case Studies</a>
    `;
  }

  render() {
    return html`
      <footer>
        <img id="logo" src="//images.monoprice.com/mp/mp-logo.svg" alt="Logo">

        <div class="footer-container">
          <div id="links">
            <div class="footer-links">
              <h2>Company</h2>
              <a href="${this.WWWDomain}/about-us" title="About Us" aria-label="about-us">About Us</a>
              <a 
                href="https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=03dbe20f-c626-4f36-b575-b5490a2d26d1&ccId=19000101_000001&type=MP&lang=en_US" 
                target="_blank" 
                title="Careers" 
                aria-label="careers"
              >
                Careers
              </a>
              <a href="${this.WWWDomain}/pages/Preferred_Rewards_Program" title="Preferred Rewards Program" aria-label="preferred-rewards-program">Preferred Rewards Program</a>
              <a href="${this.WWWDomain}/p/cat" title="Shop by Category" aria-label="shop_by_category">Shop by Category</a>
              <a href="${this.WWWDomain}/pages/td_synnex" title="Partners" aria-label="partners">Partners</a>
            </div>

            <div class="footer-links">
              <h2>Support</h2>
              <a href="https://monopricesupport.kayako.com" title="Help" aria-label="help">Help</a>
              <a href="${this.WWWDomain}/help?pn=contact" title="Contact Us" aria-label="contact-us">Contact Us</a>
              <a href="https://monopricesupport.kayako.com/section/8-returns" title="Returns" aria-label="returns">Returns</a>
              <a href="https://mpcmrrecall.com" title="Recalls" aria-label="recalls">Recalls</a>

              <slot name="a11y-link" @slotchange=${this._wireA11yLink}></slot>

              ${this._hasA11ySlot ? '' : html`
                <a role="button" href="#" @click=${this.openMenu}
                   title="Accessibility" aria-label="accessibility">Accessibility</a>
              `}

              <a href="${this.WWWDomain}/pages/MP_Academy" title="Monoprice Academy" aria-label="monoprice-academy">Monoprice Academy</a>
              <a href="${this.WWWDomain}/p/resources" title="Learning Resources" aria-label="learning_resources">Learning Resources</a>
            </div>

            <div class="footer-links">
              ${this.renderBusinessLinks()}
            </div>
          </div>

          ${this.renderEmailSignup()}
        </div>

        <div class="footer-bottom">
          <div>© 2001-${new Date().getFullYear()} Monoprice, Inc. All rights reserved. <span style="color:#212121">w${this.serverSetting}</span></div>
          <div class="footer-bottom-links">
            <a href="${this.WWWDomain}/privacy" title="Privacy Policy" aria-label="privacy">Privacy Policy</a>
            <a 
              href="${this.WWWDomain}/pages/ccpa_request" 
              title="Your Privacy Choices" 
              aria-label="privacy-choices"
            >
              Your Privacy Choices 
              <img src="https://images.monoprice.com/cms_images/privacyoptions29x14.png" />
            </a>
            <a href="${this.WWWDomain}/terms-of-use" title="Terms of Use" aria-label="terms-of-use">Terms of Use</a>
            <a href="${this.WWWDomain}/help/index?pn=compliance" title="Supplier Integrity" aria-label="supplier-integrity">Supplier Integrity</a>
            <button id="ot-sdk-btn" class="ot-sdk-show-settings last" title="Cookie Settings" role="button" @click=${this.openCookieSettings}>View Cookie Preferences</button>
          </div>
        </div>
      </footer>
    `;
  }
}

customElements.define('monoprice-footer', MonopriceFooter);
export default MonopriceFooter;
