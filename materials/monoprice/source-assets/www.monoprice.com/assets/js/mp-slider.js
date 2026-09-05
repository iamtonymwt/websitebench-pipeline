$(document).ready(function () {
    let slideIndex = 0;
    let slideCount = $('.banner-slider-img').length;
    let oriSlideCount = slideCount;
    let isAnimating = false; 
    let threshold = 50;
    let sliderTime = 5000;

    let maxDots = 5;

    let $sliderContainer = $('.banner-slider');
    let isMobile = window.matchMedia('(max-width: 768px)').matches;

    if (slideCount <= 1) {
        $('.dot').hide();
        $('.prev, .next').hide();
    } else if (slideCount <= maxDots) {
        $('.dot:gt(' + (slideCount - 1) + ')').hide();
    }

    $(".banner-slider").on("touchstart", function (event) {
        startX = event.touches[0].clientX;
    });

    $(".banner-slider").on("touchend", function (event) {
        endX = event.changedTouches[0].clientX;
        let deltaX = startX - endX;

        clearInterval(interval);
        if (deltaX > threshold) {
            showNextSlide();
        } else if (deltaX < -threshold) {
            showPrevSlide();
        }
        interval = setInterval(showNextSlide, sliderTime);
    });


    $('.dot').eq(slideIndex).addClass('active');

    function showNextSlide() {
        if (!isAnimating) {
            isAnimating = true;
            slideIndex = (slideIndex + 1) % slideCount;
            updateSlider();
        }
    }

    function showPrevSlide() {
        if (!isAnimating) {
            isAnimating = true;
            slideIndex = (slideIndex - 1 + slideCount) % slideCount;
            updateSlider();
        }
    }

    function updateSlider() {
        var sliderWidth = 100;

        var translateValue = -slideIndex * sliderWidth;
        $('.banner-slider').css({
            'transform': 'translateX(' + translateValue + '%)',
            'transition': 'transform 0.5s ease'
        });

        setTimeout(function () {
            isAnimating = false;
        }, 500);

        if (slideIndex === slideCount - 1 && oriSlideCount > 1) {
            $('.banner-slider-img').each(function () {
                var $clone = $(this).clone();
                $sliderContainer.append($clone);
                slideCount++;
            });
             
        }

        updateDots();
    }

    function updateDots() {
        $('.dot').removeClass('active');
        var activeIndex = slideIndex % oriSlideCount;
        $('.dot').eq(activeIndex).addClass('active');
    }

    $('.next').click(showNextSlide);
    $('.prev').click(showPrevSlide);

    var interval = setInterval(showNextSlide, sliderTime);

    $('.banner-slider-container').hover(
        function () {
            clearInterval(interval);
        },
        function () {
            interval = setInterval(showNextSlide, sliderTime);
           
        }
    );

    if (!isMobile) {
        $('.dot').click(function () {
            var dotIndex = $(this).index();
            if (dotIndex !== slideIndex) {
                slideIndex = dotIndex;

                var slideWidth = $('.banner-slider').width();
                var translateValue = -slideIndex * slideWidth;
                $('.banner-slider').css('transform', 'translateX(' + translateValue + 'px)');

                updateDots();
            }
        });
    }
    
    function updateImageSource() {

        const images = document.querySelectorAll(".img-responsive");
        images.forEach((img) => {
            const src = img.getAttribute("src");
            let newSrc = src;

            if (window.innerWidth < 992) {
                newSrc = src.replace("1770x570", "1190x1260");
            } else {
                newSrc = src.replace("1190x1260", "1770x570");
            }

            img.setAttribute("src", newSrc);
        });

    }

    updateImageSource();

    window.addEventListener("resize", () => {
        updateImageSource();
    });
});