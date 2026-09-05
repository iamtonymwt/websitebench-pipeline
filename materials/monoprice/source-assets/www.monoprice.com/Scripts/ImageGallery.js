import { LitElement, html, css } from './lit-all.min.js';

export default class ImageGallery extends LitElement {
  static get properties() {
    return {
      media: { type: Array },
      selectedIndex: { type: Number },
      hoveredIndex: { type: Number },
      maxThumbnailSliderDisplay: { type: Number }
    };
  }

  constructor() {
    super();
    this.media = [];
    this.selectedIndex = 0;
    this.hoveredIndex = 0;
    this.maxThumbnailSliderDisplay = 4;
    this.touchStartX = 0;
    this.touchStartY = 0;
    this.touchEndX = 0;
    this.touchEndY = 0;
    this.touchStartTime = 0;
    this.isHorizontalSwipe = false;
    this.slideAnimationDuration = 240;
  }

  getDistance(touches) {
    const [touch1, touch2] = touches;
    const dx = touch2.clientX - touch1.clientX;
    const dy = touch2.clientY - touch1.clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  handleMouseMove(event) {
    const container = event.currentTarget;
    const mainImage = container.querySelector('.main-media');
    const zoomPreview = this.shadowRoot.querySelector('.zoom-preview');
    const rect = mainImage.getBoundingClientRect();

    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const xPercent = (x / rect.width) * 100;
    const yPercent = (y / rect.height) * 100;

    zoomPreview.style.backgroundPosition = `${xPercent}% ${yPercent}%`;
  }

  handleMouseOut() {
    const zoomPreview = this.shadowRoot.querySelector('.zoom-preview');
    zoomPreview.style.display = 'none';
  }

  handleMouseEnter(event) {
    const container = event.currentTarget;
    const mainImage = container.querySelector('.main-media');
    const zoomPreview = this.shadowRoot.querySelector('.zoom-preview');
    zoomPreview.style.backgroundImage = `url(${mainImage.src})`;
    zoomPreview.style.backgroundSize = '225%';
    zoomPreview.style.display = 'block';
  }

  handleThumbnailClick(index) {
    if (index > this.selectedIndex) {
      this.runSlideAnimation('next');
    } else if (index < this.selectedIndex) {
      this.runSlideAnimation('prev');
    }
    this.selectedIndex = index;
    this.hoveredIndex = index;
  }

  handleMainImageClick() {
    this.selectedIndex = this.hoveredIndex;
    this.shadowRoot.querySelector('lightbox-component').toggleLightbox();
  }

  prevImage() {
    this.selectedIndex = (this.selectedIndex - 1 + this.media.length) % this.media.length;
    this.hoveredIndex = this.selectedIndex;
    this.runSlideAnimation('prev');
  }

  nextImage() {
    this.selectedIndex = (this.selectedIndex + 1) % this.media.length;
    this.hoveredIndex = this.selectedIndex;
    this.runSlideAnimation('next');
  }

  runSlideAnimation(direction) {
    this.updateComplete.then(() => {
      const slideTarget = this.shadowRoot.querySelector('.main-media-slide-target');
      if (!slideTarget || typeof slideTarget.animate !== 'function') {
        return;
      }

      const fromX = direction === 'next' ? '32px' : '-32px';
      slideTarget.animate(
        [
          { transform: `translateX(${fromX})`, opacity: 0.45 },
          { transform: 'translateX(0px)', opacity: 1 }
        ],
        {
          duration: this.slideAnimationDuration,
          easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)'
        }
      );
    });
  }

  handleTouchStart(event) {
    this.touchStartX = event.touches[0].clientX;
    this.touchStartY = event.touches[0].clientY;
    this.touchEndX = this.touchStartX;
    this.touchEndY = this.touchStartY;
    this.touchStartTime = new Date().getTime();
    this.isHorizontalSwipe = false;
  }

  handleTouchMove(event) {
    this.touchEndX = event.touches[0].clientX;
    this.touchEndY = event.touches[0].clientY;

    const dx = this.touchEndX - this.touchStartX;
    const dy = this.touchEndY - this.touchStartY;

    if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
      this.isHorizontalSwipe = true;
      event.preventDefault();
    }
  }

  handleTouchEnd() {
    const touchEndTime = new Date().getTime();
    const touchDuration = touchEndTime - this.touchStartTime;

    const touchDistance = Math.abs(this.touchStartX - this.touchEndX);
    const verticalDistance = Math.abs(this.touchStartY - this.touchEndY);

    if (!this.isHorizontalSwipe && touchDuration < 220 && touchDistance < 12 && verticalDistance < 12) {
      this.handleMainImageClick();
    } else {
      if (this.touchStartX - this.touchEndX > 65 && touchDistance > verticalDistance) {
        this.nextImage();
      }
      if (this.touchStartX - this.touchEndX < -65 && touchDistance > verticalDistance) {
        this.prevImage();
      }
    }

    this.isHorizontalSwipe = false;
  }

  static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
            overflow-x: clip;
        }

        .gallery-container {
            display: flex;
            gap: 2rem;
            width: 100%;
            padding: 20px;
            overflow-x: hidden;
        }

        .gallery {
            display: flex;
            flex-direction: column;
            align-items: center;
            position: relative;
            gap: 15px;
            width: 100%;
            max-width: 750px;
        }

        .main-media {
            display: flex;
            width: 100%;
            max-width: 750px;
            margin-bottom: 10px;
            cursor: crosshair;
        }

        iframe.main-media {
            min-height: 500px;
        }

        .main-media-container {
            position: relative;
            width: 100%;
            cursor: crosshair;
            touch-action: pan-y pinch-zoom;
            will-change: transform;
        }

        .touch-overlay {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 2;
            background: transparent;
            pointer-events: none;
        }

        .zoom-preview {
            width: 750px;
            height: 750px;
            border: 1px solid #ccc;
            background-repeat: no-repeat;
            position: absolute;
            left: calc(50% + 400px);
            top: 20px;
            border-radius: 4px;
            background-color: #fff;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: none;
            z-index: 999;
        }

        .thumbnail-slider-container {
            display: flex;
            width: 100%;
            max-width: 430px;
            position: relative;
        }

        .thumbnail-slider {
            display: flex;
            flex-direction: row;
            overflow-x: hidden;
            justify-content: center;
            align-items: center;
            width: 100%;
        }

        .thumbnail {
            width: 4rem;
            height: auto;
            margin: 5px;
            cursor: pointer;
            transition: 0.13s all ease-in-out;
            border: 2px solid transparent;
        }

        .thumbnail:hover {
            border: 2px solid #00000030;
        }

        .thumbnail:active {
            transform: scale(.95);
        }

        .thumbnail.selected {
            border: 2px solid #0098aa50;
        }

        .arrow {
            font-size: 2rem;
            color: #000;
            background: transparent;
            border: none;
            cursor: pointer;
            width: 30px;
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

        .pagination-dots {
            display: none;
            justify-content: center;
            align-items: center;
            gap: 6px;
            margin-top: 10px;
            width: 100%;
        }

        .pagination-dots .arrow {
            margin: 0 8px;
            width: 24px;
        }

        .pagination-dots .arrow:hover {
            background: transparent;
        }

        .mobile-thumb-dot {
            width: 34px;
            height: 34px;
            padding: 0;
            border: 1px solid #d7d7d7;
            background: #fff;
            border-radius: 4px;
            cursor: pointer;
            overflow: hidden;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            transition: border-color 0.18s ease-in-out, box-shadow 0.18s ease-in-out;
        }

        .mobile-thumb-dot.active {
            border-color: #0098aa;
            box-shadow: 0 0 0 1px #0098aa inset;
        }

        .mobile-thumb-dot img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        @media (max-width: 1600px) {
            .zoom-preview {
                width: 650px;
                height: 650px;
                left: calc(50% + 350px);
            }
        }

        @media (max-width: 1400px) {
            .zoom-preview {
                width: 550px;
                height: 550px;
                left: calc(50% + 300px);
            }
        }

        @media (max-width: 1200px) {
            .gallery-container {
                flex-direction: column;
            }

            .main-media-container {
                touch-action: pan-y;
            }

            .zoom-preview {
                display: none !important;
            }

            iframe.main-media {
                pointer-events: auto;
            }

            .main-media-container.video {
                touch-action: none;
            }

            .touch-overlay {
                display: block;
                pointer-events: auto;
            }
        }

        @media (max-width: 600px) {
            .main-media {
                max-width: 100%;
            }

            .thumbnail {
                width: 60px;
            }

            .arrow {
                width: 20px;
            }

            .pagination-dots {
                display: flex;
                overflow-x: hidden;
                justify-content: center;
                padding: 2px 0;
            }

            .thumbnail-slider-container {
                display: none;
            }

            .gallery {
                gap: 10px;
            }
        }
    `;

  renderThumbnails() {
    const totalMedia = this.media.length;
    let startIndex = Math.max(0, this.selectedIndex - Math.floor(this.maxThumbnailSliderDisplay / 2));
    let endIndex = startIndex + this.maxThumbnailSliderDisplay;

    if (endIndex > totalMedia) {
      endIndex = totalMedia;
      startIndex = Math.max(0, endIndex - this.maxThumbnailSliderDisplay);
    }

    return this.media.slice(startIndex, endIndex).map(
      (item, index) => html`
                <img
                    src=${item.type === 'video' ? item.thumbnail : item.url}
                    alt=${item.alt}
                    class="thumbnail ${this.hoveredIndex === (startIndex + index) ? 'selected' : ''}"
                    @click=${() => this.handleThumbnailClick(startIndex + index)}
                />
            `
    );
  }

  renderPaginationDots() {
    return this.media.map(
      (item, index) => html`
                <button
                    type="button"
                    class="mobile-thumb-dot ${this.selectedIndex === index ? 'active' : ''}"
                    @click=${() => this.handleThumbnailClick(index)}
                    aria-label=${`View image ${index + 1}`}
                >
                    <img
                        src=${item.type === 'video' ? item.thumbnail : item.url}
                        alt=${item.alt}
                    />
                </button>
            `
    );
  }

  renderMainMedia() {
    const selectedMedia = this.media[this.hoveredIndex];
    if (!selectedMedia) {
      return html`<div class="main-media">No media available</div>`;
    }
    if (selectedMedia.type === 'video') {
      return html`
                <div class="main-media-container main-media-slide-target video">
                    <iframe
                        src=${selectedMedia.url}
                        class="main-media"
                        frameborder="0"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowfullscreen
                        alt=${selectedMedia.alt}
                    ></iframe>
                </div>
            `;
    } else {
      return html`
                <div class="main-media-container main-media-slide-target" 
                    @mousemove=${this.handleMouseMove}
                    @mouseenter=${this.handleMouseEnter}
                    @mouseleave=${this.handleMouseOut}
                    @touchstart=${this.handleTouchStart}
                    @touchmove=${this.handleTouchMove}
                    @touchend=${this.handleTouchEnd}>
                    <img 
                        src=${selectedMedia.url} 
                        class="main-media" 
                        alt=${selectedMedia.alt} 
                        @click=${this.handleMainImageClick}
                    />
                </div>
            `;
    }
  }

  render() {
    return html`
            <div class="gallery-container">
                <div class="gallery">
                    ${this.renderMainMedia()}
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
                    <div class="pagination-dots">
                        <button class="arrow" @click=${this.prevImage}>
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="#000" class="bi bi-chevron-left" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M11.354 1.646a.5.5 0 0 1 0 .708L5.707 8l5.647 5.646a.5.5 0 0 1-.708.708l-6-6a.5.5 0 0 1 0-.708l6-6a.5.5 0 0 1 .708 0z"/>
                            </svg>
                        </button>
                        ${this.renderPaginationDots()}
                        <button class="arrow" @click=${this.nextImage}>
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="#000" class="bi bi-chevron-right" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/>
                            </svg>
                        </button>
                    </div>
                    <lightbox-component .images=${this.media} .selectedIndex=${this.selectedIndex}></lightbox-component>
                </div>
                <div class="zoom-preview"></div>
            </div>
        `;
  }
}

customElements.define('image-gallery', ImageGallery);
