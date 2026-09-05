var swiper1 = {};
var swiper2 = {};
var swiper3 = {};

var productPageStuff = {
    oldInit: function () {
        $(document).ready(function () {
            $(".custom-loader").hide();
            $(".product-item a").show();

        });

        var swiper1 = new Swiper("#product-slider-regular1",
            {
                slidesPerView: 6,
                slidesPerGroup: 6,
                loopFillGroupWithBlank: true,
                loop: true,
                grabCursor: true,
                navigation: {
                    nextEl: ".swiper-button-next",
                    prevEl: ".swiper-button-prev",
                },
                pagination: {
                    el: ".swiper-pagination",
                    clickable: true,
                },
                breakpoints: {
                    1024: {
                        slidesPerView: 5,
                        spaceBetween: 40,
                        slidesPerGroup: 5,
                    },
                    768: {
                        slidesPerView: 3,
                        spaceBetween: 30,
                        slidesPerGroup: 3,
                    },
                    640: {
                        slidesPerView: 2,
                        spaceBetween: 20,
                        slidesPerGroup: 2,
                    },
                    320: {
                        slidesPerView: 1,
                        spaceBetween: 10,
                        slidesPerGroup: 1,
                    }
                }
            });
        CustomTabbingForSlider("#product-slider-regular1", "#tab1", "#tab3", swiper1);
    },
    contentFills: [
        {
            url: "/product/GetCustomersAlsoShoppedFor",
            outerContainerSelector: "#AlsoBought",
            innerContainerSelector: "#AlsoBought",
            onSuccess: function() {
                // Show/hide disabled

                $(".custom-loader").hide();
                $(".product-item a").show();
                swiper1 = new Swiper("#product-slider-regular1",
                {
                    slidesPerView: 6,
                    slidesPerGroup: 6,   
                    loopFillGroupWithBlank: true,                                         
                    loop: true,
                    grabCursor: true,
                    touchEventsTarget: 'container',
                    navigation: {
                        nextEl: ".swiper-button-next",
                        prevEl: ".swiper-button-prev",
                    },
                    pagination: {
                        el: ".swiper-pagination",
                    },
                    breakpoints: {
                        1024: {
                            slidesPerView: 5,
                            spaceBetween: 40,
                            slidesPerGroup: 5,
                        },
                        768: {
                            slidesPerView: 3,
                            spaceBetween: 30,
                            slidesPerGroup: 3,
                        },
                        640: {
                            slidesPerView: 2,
                            spaceBetween: 20,
                            slidesPerGroup: 2,
                        },
                        320: {
                            slidesPerView: 1,
                            spaceBetween: 10,
                            slidesPerGroup: 1,
                        }
                    },
                    on: {                        
                        resize: function() {
                            // Show/hide disabled
                            ShowHidePaginationSwiper(swiper1, "#product-slider-regular1");
                        }
                    }
                });

                ShowHidePaginationSwiper(swiper1, "#product-slider-regular1");

                CustomTabbingForSlider("#product-slider-regular1", "#tab1", "#tab3", swiper1);
            }
        },
         {
            url: "/product/getrecommendationsforyou",
            outerContainerSelector: "#RecommandationsForYou",
            innerContainerSelector: "#RecommandationsForYou",
            onSuccess: function() {
                swiper2 = new Swiper("#product-slider-regular2",
                {
                    slidesPerView: 6,
                    slidesPerGroup: 6,
                    loopFillGroupWithBlank: true,
                    loop: true,
                    grabCursor: true,
                    navigation: {
                        nextEl: ".swiper-button-next",
                        prevEl: ".swiper-button-prev",
                    },
                    pagination: {
                        el: ".swiper-pagination",
                    },
                    breakpoints: {
                        1024: {
                            slidesPerView: 5,
                            spaceBetween: 40,
                            slidesPerGroup: 5,
                        },
                        768: {
                            slidesPerView: 3,
                            spaceBetween: 30,
                            slidesPerGroup: 3,
                        },
                        640: {
                            slidesPerView: 2,
                            spaceBetween: 20,
                            slidesPerGroup: 2,
                        },
                        320: {
                            slidesPerView: 1,
                            spaceBetween: 10,
                            slidesPerGroup: 1,
                        }
                    },
                    on: {                        
                        resize: function() {
                            checkSlidesProductpage('#product-slider-regular2',$("#product-slider-regular2").attr("data-total"));
                        }
                    }
                });
                CustomTabbingForSlider("#product-slider-regular2", "#tab3", "#tab5", swiper2);
            }
        },
        {
            url: "/product/getrecentlyviewed",
            outerContainerSelector: "#RecentlyViewed",
            innerContainerSelector: "#RecentlyViewed",
            onSuccess: function () {
                swiper3 = new Swiper("#product-slider-regular3",
                {
                    slidesPerView: 6,
                    slidesPerGroup: 6,
                    loopFillGroupWithBlank: true,
                    loop: true,
                    grabCursor: true,
                    navigation: {
                        nextEl: ".swiper-button-next",
                        prevEl: ".swiper-button-prev",
                    },
                    pagination: {
                        el: ".swiper-pagination",
                    },
                    breakpoints: {
                        1024: {
                            slidesPerView: 5,
                            spaceBetween: 40,
                            slidesPerGroup: 5,
                        },
                        768: {
                            slidesPerView: 3,
                            spaceBetween: 30,
                            slidesPerGroup: 3,
                        },
                        640: {
                            slidesPerView: 2,
                            spaceBetween: 20,
                            slidesPerGroup: 2,
                        },
                        320: {
                            slidesPerView: 1,
                            spaceBetween: 10,
                            slidesPerGroup: 1,
                        }
                    },
                    on: {                       
                        resize: function() {
                            checkSlidesProductpage('#product-slider-regular3',$("#product-slider-regular3").attr("data-total"));
                        }
                    }
                });
                CustomTabbingForSlider("#product-slider-regular3", "#tab3", "#tab5", swiper3);
            }
        }       
    ],
    getUnbxdContent: function(options) {
        for (var i = 0; i < productPageStuff.contentFills.length; i++) {
            var outerItem = productPageStuff.contentFills[i];
            //wrap item in closure for after ajax call finishes.
            (function(item) {
                $(item.outerContainerSelector).hide();
                $.ajax({
                    url: item.url +
                        "?p_id=" +
                        options.p_id +
                        "&cust_review=" +
                        options.cust_review,

                    success: function(data) {
                        if (data) {
                            $(item.innerContainerSelector).html(data);
                            $(item.outerContainerSelector + " .product-item a").show();
                            $(item.outerContainerSelector + " .custom-loader").hide();
                            $(item.outerContainerSelector + " *").css("opacity", "");
                            $(item.outerContainerSelector).show();
                            if (item.onSuccess) {
                                item.onSuccess();
                            }

                        }
                    }
                });
            })(outerItem);
        }
    },
    initialize: function(options) {
        if (options.unbxdVersion === unbxdVersionValue) {
            productPageStuff.getUnbxdContent(options);
        }
        for (var tabIndex = 1; tabIndex < 6; tabIndex++) {
            if (tabIndex === 4 || tabIndex === 2) {
                continue;
            }

            var outerItem = {
                tabUrl: "/Product/GetTab" +
                    tabIndex +
                    "?p_id=" +
                    options.p_id +
                    "&cust_review=" +
                    options.cust_review,
                selector: "#tab" + tabIndex,
                index: tabIndex
            };

            //wrap in closure
            (function(item) {
                $.ajax({
                    url: item.tabUrl,
                    datatype: "json",
                    type: "post",
                    contenttype: "application/json; charset=utf-8",
                    async: true,
                    success: function(data) {
                        $(".loader").hide();
                        if (item.index === 3) {
                            $("#qaTab").parent(".tab-content").prepend(data);
                            $("#tab3").show();
                        } else {
                            $(item.selector).html(data);
                        }

                    }
                });
            })(outerItem);
        }
        productPageStuff.oldInit();
    }
}

function checkSlidesProductpage(sliderName,sliderCount) {
    var slidesRowCount = 0;
    if(sliderName == "#product-slider-regular1") {
        slidesRowCount = swiper1.loopedSlides;
    } 
    else if(sliderName == "#product-slider-regular2") {
        slidesRowCount = swiper2.loopedSlides;
    } 
    else if(sliderName == "#product-slider-regular3") {
        slidesRowCount = swiper3.loopedSlides;
    }

    if (slidesRowCount < parseInt(sliderCount)) {
        $(sliderName + ' .swiper-pagination').show();
        $(sliderName + ' .swiper-wrapper').removeClass("disabled");
    }
    else {       
        $(sliderName + ' .swiper-pagination').hide();
        $(sliderName + ' .swiper-wrapper').addClass("disabled");
        $(sliderName + ' .swiper-slide-invisible-blank').remove();
    }
}

window.onload = function() {
    ShowHidePaginationSwiper(swiper1, "#product-slider-regular1");
    checkSlidesProductpage('#product-slider-regular2', $("#product-slider-regular2").attr("data-total"));
    checkSlidesProductpage('#product-slider-regular3', $("#product-slider-regular3").attr("data-total"));
};

function ShowHidePaginationSwiper(swiper, id) {
    let sliderCapacity = swiper.loopedSlides;
    let productsRecommended = parseInt($(id).attr("data-total"));

    if (productsRecommended <= sliderCapacity) {
        swiper.disable();
    } else {
        swiper.enable();
    }
    swiper.updateSize();
    swiper.update();
}