import { LitElement, html, css } from './lit-all.min.js';

export default class Lightbox extends LitElement {
    static get properties() {
        return {
            images: { type: Array },
            selectedIndex: { type: Number },
            open: { type: Boolean }
        };
    }

    constructor() {
        super();
        this.images = [];
        this.selectedIndex = 0;
        this.open = false;
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.touchStartTime = 0;
        this.lastTap = 0;
        this.scale = 1;
        this.minScale = 1;
        this.maxScale = 4;
        this.translateX = 0;
        this.translateY = 0;
        this.isPanning = false;
        this.isPinching = false;
        this.pinchStartDistance = 0;
        this.pinchStartScale = 1;
        this.panStartX = 0;
        this.panStartY = 0;
        this.baseTranslateX = 0;
        this.baseTranslateY = 0;
        this.scrollLockY = 0;
        this.savedBodyStyles = null;
        this.savedHtmlOverflow = '';
        this.viewportMeta = null;
        this.savedViewportContent = '';
        this.slideAnimationDuration = 240;

        this.toggleLightbox = this.toggleLightbox.bind(this);
        this.nextImage = this.nextImage.bind(this);
        this.prevImage = this.prevImage.bind(this);
        this.handleTouchStart = this.handleTouchStart.bind(this);
        this.handleTouchMove = this.handleTouchMove.bind(this);
        this.handleTouchEnd = this.handleTouchEnd.bind(this);
        this.handleLayerTap = this.handleLayerTap.bind(this);
        this.preventNativeZoom = this.preventNativeZoom.bind(this);
        this.preventDocumentTouchMove = this.preventDocumentTouchMove.bind(this);
    }

    disconnectedCallback() {
        if (this.open) {
            this.unlockBodyScroll();
        }
        super.disconnectedCallback();
    }

    updated(changedProperties) {
        if (changedProperties.has('open')) {
            if (this.open) {
                this.lockBodyScroll();
                this.resetTransform();
            } else {
                this.unlockBodyScroll();
                this.resetTransform();
            }
        }
    }

    getDistance(touches) {
        if (touches.length < 2) {
            return 0;
        }

        const dx = touches[1].clientX - touches[0].clientX;
        const dy = touches[1].clientY - touches[0].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    preventNativeZoom(event) {
        if (this.open) {
            event.preventDefault();
        }
    }

    preventDocumentTouchMove(event) {
        if (!this.open) {
            return;
        }

        const eventPath = event.composedPath ? event.composedPath() : [];
        const isInMediaFrame = eventPath.some(
            (node) => node && node.classList && node.classList.contains('lightbox-media-frame')
        );

        if (event.touches && event.touches.length > 1) {
            event.preventDefault();
            return;
        }

        if (!isInMediaFrame) {
            event.preventDefault();
        }
    }

    lockBodyScroll() {
        if (this.savedBodyStyles) {
            return;
        }

        const bodyStyle = document.body.style;
        this.scrollLockY = window.scrollY || window.pageYOffset || 0;
        this.savedBodyStyles = {
            position: bodyStyle.position,
            top: bodyStyle.top,
            left: bodyStyle.left,
            right: bodyStyle.right,
            width: bodyStyle.width,
            overflow: bodyStyle.overflow
        };
        this.savedHtmlOverflow = document.documentElement.style.overflow;

        bodyStyle.position = 'fixed';
        bodyStyle.top = `-${this.scrollLockY}px`;
        bodyStyle.left = '0';
        bodyStyle.right = '0';
        bodyStyle.width = '100%';
        bodyStyle.overflow = 'hidden';
        document.documentElement.style.overflow = 'hidden';

        this.viewportMeta = document.querySelector('meta[name="viewport"]');
        if (this.viewportMeta) {
            this.savedViewportContent = this.viewportMeta.getAttribute('content') || '';
            let sanitizedViewport = this.savedViewportContent
                .replace(/\s*maximum-scale\s*=\s*[^,]+,?/gi, '')
                .replace(/\s*minimum-scale\s*=\s*[^,]+,?/gi, '')
                .replace(/\s*user-scalable\s*=\s*[^,]+,?/gi, '')
                .replace(/,\s*,/g, ',')
                .replace(/^,|,$/g, '')
                .trim();

            if (sanitizedViewport.length > 0) {
                sanitizedViewport += ', ';
            }

            this.viewportMeta.setAttribute('content', `${sanitizedViewport}maximum-scale=1, user-scalable=no`);
        }

        document.addEventListener('gesturestart', this.preventNativeZoom, { passive: false });
        document.addEventListener('gesturechange', this.preventNativeZoom, { passive: false });
        document.addEventListener('gestureend', this.preventNativeZoom, { passive: false });
        document.addEventListener('touchmove', this.preventDocumentTouchMove, { passive: false });
    }

    unlockBodyScroll() {
        if (!this.savedBodyStyles) {
            return;
        }

        const bodyStyle = document.body.style;
        bodyStyle.position = this.savedBodyStyles.position;
        bodyStyle.top = this.savedBodyStyles.top;
        bodyStyle.left = this.savedBodyStyles.left;
        bodyStyle.right = this.savedBodyStyles.right;
        bodyStyle.width = this.savedBodyStyles.width;
        bodyStyle.overflow = this.savedBodyStyles.overflow;
        document.documentElement.style.overflow = this.savedHtmlOverflow;
        window.scrollTo(0, this.scrollLockY);

        if (this.viewportMeta) {
            this.viewportMeta.setAttribute('content', this.savedViewportContent);
            this.viewportMeta = null;
            this.savedViewportContent = '';
        }

        document.removeEventListener('gesturestart', this.preventNativeZoom);
        document.removeEventListener('gesturechange', this.preventNativeZoom);
        document.removeEventListener('gestureend', this.preventNativeZoom);
        document.removeEventListener('touchmove', this.preventDocumentTouchMove);

        this.savedBodyStyles = null;
        this.savedHtmlOverflow = '';
    }

    resetTransform() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.isPanning = false;
        this.isPinching = false;
    }

    clampPan() {
        const frame = this.shadowRoot && this.shadowRoot.querySelector('.lightbox-media-frame');
        if (!frame) {
            return;
        }

        const maxX = ((this.scale - 1) * frame.clientWidth) / 2;
        const maxY = ((this.scale - 1) * frame.clientHeight) / 2;

        this.translateX = Math.max(-maxX, Math.min(this.translateX, maxX));
        this.translateY = Math.max(-maxY, Math.min(this.translateY, maxY));
    }

    toggleLightbox() {
        this.open = !this.open;
    }

    handleLayerTap(event) {
        event.stopPropagation();

        const interactiveTarget = event.target.closest(
            '.lightbox-media-frame, .lightbox-media, iframe.lightbox-media, #closeLightbox, .thumbnail-slider-container, .thumbnail-slider, .thumbnail, .arrow'
        );

        if (interactiveTarget) {
            return;
        }

        this.toggleLightbox();
    }

    nextImage() {
        this.selectedIndex = (this.selectedIndex + 1) % this.images.length;
        this.resetTransform();
        this.runSlideAnimation('next');
    }

    prevImage() {
        this.selectedIndex = (this.selectedIndex - 1 + this.images.length) % this.images.length;
        this.resetTransform();
        this.runSlideAnimation('prev');
    }

    runSlideAnimation(direction) {
        this.updateComplete.then(() => {
            const slideTarget = this.shadowRoot.querySelector('.lightbox-media-frame');
            if (!slideTarget || typeof slideTarget.animate !== 'function') {
                return;
            }

            const fromX = direction === 'next' ? '36px' : '-36px';
            slideTarget.animate(
                [
                    { transform: `translate3d(${fromX}, 0, 0)` },
                    { transform: 'translate3d(0, 0, 0)' }
                ],
                {
                    duration: this.slideAnimationDuration,
                    easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)'
                }
            );
        });
    }

    handleTouchStart(event) {
        if (!this.images[this.selectedIndex] || this.images[this.selectedIndex].type === 'video') {
            return;
        }

        if (event.touches.length === 2) {
            event.preventDefault();
            this.isPinching = true;
            this.isPanning = false;
            this.pinchStartDistance = this.getDistance(event.touches);
            this.pinchStartScale = this.scale;
            return;
        }

        const touch = event.touches[0];
        this.touchStartX = touch.clientX;
        this.touchStartY = touch.clientY;
        this.touchEndX = touch.clientX;
        this.touchEndY = touch.clientY;
        this.touchStartTime = Date.now();

        if (this.scale > 1) {
            this.isPanning = true;
            this.panStartX = touch.clientX;
            this.panStartY = touch.clientY;
            this.baseTranslateX = this.translateX;
            this.baseTranslateY = this.translateY;
        }
    }

    handleTouchMove(event) {
        if (!this.images[this.selectedIndex] || this.images[this.selectedIndex].type === 'video') {
            return;
        }

        if (event.touches.length === 2 && this.isPinching) {
            event.preventDefault();
            const currentDistance = this.getDistance(event.touches);

            if (this.pinchStartDistance > 0) {
                const nextScale = this.pinchStartScale * (currentDistance / this.pinchStartDistance);
                this.scale = Math.max(this.minScale, Math.min(nextScale, this.maxScale));
                this.clampPan();
            }
            return;
        }

        if (event.touches.length !== 1) {
            return;
        }

        const touch = event.touches[0];
        this.touchEndX = touch.clientX;
        this.touchEndY = touch.clientY;
        const dx = this.touchEndX - this.touchStartX;
        const dy = this.touchEndY - this.touchStartY;

        if (this.scale > 1 && this.isPanning) {
            event.preventDefault();
            this.translateX = this.baseTranslateX + (touch.clientX - this.panStartX);
            this.translateY = this.baseTranslateY + (touch.clientY - this.panStartY);
            this.clampPan();
            return;
        }

        if (Math.abs(dx) > Math.abs(dy)) {
            event.preventDefault();
        }
    }

    handleTouchEnd(event) {
        if (!this.images[this.selectedIndex] || this.images[this.selectedIndex].type === 'video') {
            return;
        }

        if (event.changedTouches && event.changedTouches.length) {
            this.touchEndX = event.changedTouches[0].clientX;
            this.touchEndY = event.changedTouches[0].clientY;
        }

        const now = Date.now();
        const dx = this.touchEndX - this.touchStartX;
        const dy = this.touchEndY - this.touchStartY;
        const absX = Math.abs(dx);
        const absY = Math.abs(dy);
        const duration = now - this.touchStartTime;

        if (this.isPinching) {
            this.isPinching = false;
            if (this.scale <= 1.05) {
                this.resetTransform();
            } else {
                this.clampPan();
            }
            return;
        }

        if (this.scale > 1 && this.isPanning) {
            this.isPanning = false;
            this.clampPan();

            if (absX < 10 && absY < 10 && duration < 250) {
                if (now - this.lastTap < 300) {
                    this.resetTransform();
                    this.lastTap = 0;
                } else {
                    this.lastTap = now;
                }
            }
            return;
        }

        if (this.scale <= 1.05 && duration < 500 && absX > 50 && absX > absY) {
            if (dx < 0) {
                this.nextImage();
            } else {
                this.prevImage();
            }
            return;
        }

        if (absX < 12 && absY < 12 && duration < 250) {
            if (now - this.lastTap < 300) {
                this.scale = this.scale > 1 ? 1 : 2.5;
                this.translateX = 0;
                this.translateY = 0;
                this.lastTap = 0;
            } else {
                this.lastTap = now;
            }
        }
    }

    static styles = css`
    .lightbox {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.8);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 99999999999999;
      overscroll-behavior: contain;
      touch-action: none;
    }
    .lightbox-layer {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      max-width: 90%;
      max-height: 90%;
      background: #fff;
      padding: 20px;
      border-radius: 10px;
      box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
      touch-action: none;
      overflow-x: hidden;
    }
    .lightbox-content {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 15px;
      width: 100%;
      height: 100%;
    }
    .lightbox-media-frame {
      width: min(96vw, 1240px);
      height: min(74vh, 860px);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      background: #ffffff;
      touch-action: none;
      user-select: none;
      will-change: transform;
      transform: translateZ(0);
      backface-visibility: hidden;
      -webkit-backface-visibility: hidden;
    }
    .lightbox-media-frame.video-frame {
      touch-action: auto;
    }
    .lightbox-media {
      max-width: 100% !important;
      max-height: 100%;
      object-fit: contain;
      touch-action: none;
      user-select: none;
      transform-origin: center center;
      transition: none;
      backface-visibility: hidden;
      -webkit-backface-visibility: hidden;
    }
    iframe.lightbox-media {
      width: min(96vw, 1240px);
      height: min(74vh, 860px);
      max-width: 100% !important;
      touch-action: auto;
    }
    .thumbnail-slider-container {
      display: flex;
      flex-direction: row;
      align-items: center;
      height: 80px;
      width: 100%;
      justify-content: center;
    }
    .thumbnail-slider {
      display: flex;
      flex-direction: row;
      overflow-x: hidden;
      justify-content: center;
      align-items: center;
      width: 80%;
      touch-action: pan-x;
    }
    .thumbnail {
      width: 75px;
      height: auto;
      margin: 5px;
      cursor: pointer;
      transition: 0.13s all ease-in-out;
      border: 2px solid transparent;
    }
    .thumbnail:hover {
      transform: scale(1.05);
    }
    .thumbnail:active {
      transform: scale(1);
    }
    .thumbnail.selected {
      border: 2px solid #0098aa50;
    }
    .arrow {
      font-size: 2rem;
      background: transparent;
      border: none;
      cursor: pointer;
      width: 30px;
      height: 75%;
      text-align: center;
      transition: 0.13s all ease-in-out;
    }
    .arrow:hover {
      background: rgba(0, 0, 0, 0.15);
    }
    .arrow:active {
      background: rgba(0, 0, 0, 0.25);
    }
    .arrow svg {
      transform: scale(1.5);
    }
    #closeLightbox {
      position: absolute;
      top: 20px;
      right: 20px;
      font-size: 2rem;
      color: black;
      cursor: pointer;
      background: none;
      border: none;
      z-index: 9999;
    }
    @media (max-height: 1080px) {
        .lightbox-media-frame {
            height: min(68vh, 760px);
        }
        iframe.lightbox-media {
            height: min(68vh, 760px);
        }
    }
    @media (max-width: 1400px) {
        .lightbox-media-frame {
            width: min(94vw, 1120px);
            height: min(66vh, 720px);
        }
        iframe.lightbox-media {
            width: min(94vw, 1120px);
            height: min(66vh, 720px);
        }
    }
    @media (max-width: 1150px) {
        .lightbox-media-frame {
            width: min(93vw, 980px);
            height: min(62vh, 640px);
        }
        iframe.lightbox-media {
            width: min(93vw, 980px);
            height: min(62vh, 640px);
        }
    }

    @media (max-width: 900px) {
        .lightbox-media-frame {
            width: 100%;
            height: 62vh;
        }
        iframe.lightbox-media {
            width: 100%;
            height: 62vh;
        }
        .thumbnail {
            width: 60px;
        }
    }
    @media (max-width: 700px) {
      .lightbox-layer {
        width: 100%;
        height: 100%;
        max-width: none;
        max-height: none;
        border-radius: 0;
        box-shadow: none;
        background: #111;
        padding: 12px 10px 14px;
      }
      .lightbox-content {
        margin-top: 40px;
        gap: 10px;
      }
      .lightbox-media-frame {
        width: 100%;
        height: 72vh;
        background: #000;
      }
      .thumbnail-slider {
        width: 84%;
        overflow-x: hidden;
        justify-content: center;
        margin: 0 auto;
      }
      .thumbnail-slider-container {
        height: auto;
        width: 100%;
      }
      .thumbnail {
        width: 52px;
      }
      #closeLightbox {
        color: #fff;
      }
      iframe.lightbox-media {
        width: 100%;
        height: 72vh;
      }
    }
  `;


    //@mouseover=${() => this.selectedIndex = index} for hover select
    renderThumbnails() {
        return this.images.map(
            (item, index) => html`
                <img
                  src=${item.type === 'video' ? item.thumbnail : item.url}
                  alt=${item.alt}
                  class="thumbnail ${this.selectedIndex === index ? 'selected' : ''}"
                  
                  @click=${() => this.selectedIndex = index}
                />
              `
        );
    }

    renderMedia() {
        const selectedMedia = this.images[this.selectedIndex];
        if (!selectedMedia) {
            return html``;
        }

        if (selectedMedia.type === 'video') {
            return html`
                <div class="lightbox-media-frame video-frame">
                  <iframe
                    class="lightbox-media"
                    src=${selectedMedia.url}
                    frameborder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowfullscreen
                    alt=${selectedMedia.alt}
                  ></iframe>
                </div>
              `;
        } else {
            const transformStyle = `translate3d(${this.translateX}px, ${this.translateY}px, 0) scale(${this.scale})`;
            return html`
                <div
                  class="lightbox-media-frame"
                  @touchstart=${this.handleTouchStart}
                  @touchmove=${this.handleTouchMove}
                  @touchend=${this.handleTouchEnd}
                  @touchcancel=${this.handleTouchEnd}
                >
                  <img
                    src=${selectedMedia.url}
                    class="lightbox-media"
                    alt=${selectedMedia.alt}
                    style=${`transform: ${transformStyle};`}
                    draggable="false"
                  />
                </div>
            `;
        }
    }

    render() {
        return html`
              ${this.open
            ? html`
                    <div class="lightbox" @click=${this.toggleLightbox}>
                      <div class="lightbox-layer" @click=${this.handleLayerTap}>
                        <button id="closeLightbox" @click=${this.toggleLightbox}>×</button>
                        <div class="lightbox-content">
                          ${this.renderMedia()}
                          <div class="thumbnail-slider-container">
                            <button class="arrow" @click=${this.prevImage}>
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="#000" class="bi bi-chevron-left" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
                              </svg>
                            </button>
                            <div class="thumbnail-slider">
                              ${this.renderThumbnails()}
                            </div>
                            <button class="arrow" @click=${this.nextImage}>
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="#000" class="bi bi-chevron-right" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
                              </svg>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  `
                        : ''}
            `;
    }
}

customElements.define('lightbox-component', Lightbox);
