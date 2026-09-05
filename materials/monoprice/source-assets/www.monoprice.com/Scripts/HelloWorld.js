import { LitElement, html, css } from './lit-all.min.js';

class HelloWorld extends LitElement {

    constructor() {
        super();
    }

    static styles = css`
    :host {
      display: flex;
    }
  `;

    connectedCallback() {
        super.connectedCallback();
    }

    render() {
        return html`
        <h1>Hello World 1</h1>

    `;
    }
}

customElements.define("hello-world", HelloWorld);
export default HelloWorld;
