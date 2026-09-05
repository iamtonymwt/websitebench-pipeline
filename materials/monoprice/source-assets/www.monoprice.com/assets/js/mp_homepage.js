var swiper1 = {};
var swiper2 = {};
var swiper3 = {};

var homePageStuff = {
    contentFills: [
        {
            url: '/home/getRecentlyViewed',
            outerContainerSelector: '.home-layer7',
            innerContainerSelector: '#recentlyviewed',
            onSuccess: function () {
                swiper1 = new Swiper('#product-slider-regular1',
                    {
                        slidesPerView: 6,
                        loopFillGroupWithBlank: true,
                        slidesPerGroup: 6,
                        grabCursor: true,
                        loop: true,
                        navigation: {
                            nextEl: '.swiper-button-next',
                            prevEl: '.swiper-button-prev',
                        },
                        pagination: {
                            el: '.swiper-pagination',
                            clickable: true
                        },
                        breakpoints: {
                            1024: {
                                slidesPerView: 5,
                                spaceBetween: 10,
                                slidesPerGroup: 5,
                            },
                            768: {
                                slidesPerView: 4,
                                spaceBetween: 10,
                                slidesPerGroup: 4,
                            },
                            640: {
                                slidesPerView: 2,
                                spaceBetween: 10,
                                slidesPerGroup: 2,
                            },
                            320: {
                                slidesPerView: 1,
                                spaceBetween: 10,
                                slidesPerGroup: 1,
                            }
                        },
                        on: {
                            resize: function () {
                                checkSlides('#product-slider-regular1', $("#product-slider-regular1").attr("data-total"));
                            }
                        }
                    });
                const swiper = swiper1;
                swiper.loopDestroy();
                swiper.loopCreate();
                CustomTabbingForSlider("#product-slider-regular1", ".home-layer6", "footer", swiper1);
            }
        }, {
            url: '/home/getRecommendationsForYou',
            outerContainerSelector: '.home-layer3',
            innerContainerSelector: '#recommendations',
            onSuccess: function () {
                swiper2 = new Swiper('#product-slider-regular2',
                    {
                        slidesPerView: 6,
                        loopFillGroupWithBlank: true,
                        grabCursor: true,
                        slidesPerGroup: 6,
                        loop: true,
                        navigation: {
                            nextEl: '.swiper-button-next',
                            prevEl: '.swiper-button-prev',
                        },
                        pagination: {
                            el: '.swiper-pagination',
                            clickable: true
                        },
                        breakpoints: {
                            1024: {
                                slidesPerView: 5,
                                spaceBetween: 10,
                                slidesPerGroup: 5,
                            },
                            768: {
                                slidesPerView: 4,
                                spaceBetween: 10,
                                slidesPerGroup: 4,
                            },
                            640: {
                                slidesPerView: 2,
                                spaceBetween: 10,
                                slidesPerGroup: 2,
                            },
                            320: {
                                slidesPerView: 1,
                                spaceBetween: 10,
                                slidesPerGroup: 1,
                            }
                        },
                        on: {
                            resize: function () {
                                checkSlides('#product-slider-regular2', $("#product-slider-regular2").attr("data-total"));
                            }
                        }
                    });
                const swiper = swiper2;
                swiper.loopDestroy();
                swiper.loopCreate();
                CustomTabbingForSlider("#product-slider-regular2", ".home-layer2", ".home-layer4", swiper2);
            }
        }, {
            url: '/home/getTopSellers',
            outerContainerSelector: '.home-layer4',
            innerContainerSelector: '#topsellers',
            onSuccess: function () {

                swiper3 = new Swiper('#product-slider-regular3',
                    {
                        slidesPerView: 6,
                        loopFillGroupWithBlank: true,
                        slidesPerGroup: 6,
                        grabCursor: true,
                        loop: true,
                        navigation: {
                            nextEl: '.swiper-button-next',
                            prevEl: '.swiper-button-prev',
                        },
                        pagination: {
                            el: '.swiper-pagination',
                            clickable: true
                        },
                        breakpoints: {
                            1024: {
                                slidesPerView: 5,
                                spaceBetween: 10,
                                slidesPerGroup: 5,
                            },
                            768: {
                                slidesPerView: 4,
                                spaceBetween: 10,
                                slidesPerGroup: 4,
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
                            resize: function () {
                                checkSlides('#product-slider-regular3', $("#product-slider-regular3").attr("data-total"));
                            }
                        }
                    });
                const swiper = swiper3;
                swiper.loopDestroy();
                swiper.loopCreate();
                CustomTabbingForSlider("#product-slider-regular3", ".home-layer3", ".home-layer5", swiper3);
            }
        }
    ],
    someUnnamedFunction: function () {
        if (jQuery("[id^=div-ad-]").length > 0) {
            var dcJS = document.createElement('SCRIPT');
            var done = false;

            dcJS.setAttribute('src', '//securepubads.g.doubleclick.net/tag/js/gpt.js');
            dcJS.setAttribute('type', 'text/javascript');

            document.body.appendChild(dcJS);
            dcJS.onload = dcJS.onreadystatechange = function () {
                if (!done && (!this.readyState || this.readyState === "loaded" || this.readyState === "complete")) {
                    done = true;
                    callback();

                    // Handle memory leak in IE
                    dcJS.onload = dcJS.onreadystatechange = null;
                    document.body.removeChild(dcJS);
                }
            };

            /*function callback() {
                if (done) {
                    _satellite.notify("'content: all pages': Google DFP Ads");
                    var mappingLeaderboard, mappingSkyscraper, mappingLeaderRectangle;
                    var width = jQuery(window).width();

                    var resizeTimer;

                    function resizer() {
                        googletag.pubads().refresh();
                    }

                    jQuery(window).resize(function () {
                        clearTimeout(resizeTimer);
                        resizeTimer = setTimeout(resizer, 3500);
                    });

                    googletag.cmd.push(function () {
                        mappingLeaderboard = googletag.sizeMapping().addSize([775, 0], [728, 90]).//Desktop and Tablet
                            addSize([0, 0], [320, 100]).//Mobile
                            build();

                        mappingLeaderRectangle = googletag.sizeMapping().addSize([775, 0], [728, 90])
                            .//Desktop and Tablet
                            addSize([0, 0], [300, 250]).//Mobile
                            build();

                        mappingSkyscraper = googletag.sizeMapping().addSize([0, 0], [160, 600]).//Skyscraper
                            build();
                    });

                    googletag.cmd.push(function () {
                        googletag.defineSlot('/64852981/MP_Homepage_New',
                            [[320, 100], [728, 90]],
                            'div-ad-home-btf-b2c').addService(googletag.pubads())
                            .defineSizeMapping(mappingLeaderboard);
                        googletag.enableServices();
                    },
                        function () { googletag.display('div-ad-home-btf-b2c'); });

                    googletag.cmd.push(function () {
                        googletag.defineSlot('/64852981/MP_Homepage_Leg_ATF',
                            [[320, 100], [728, 90]],
                            'div-ad-home-atf-b2b').addService(googletag.pubads())
                            .defineSizeMapping(mappingLeaderboard);
                        googletag.enableServices();
                    },
                        function () { googletag.display('div-ad-home-atf-b2b'); });

                    googletag.cmd.push(function () {
                        googletag.defineSlot('/64852981/MP_Homepage_Leg_BTF',
                            [[320, 100], [728, 90]],
                            'div-ad-home-btf-b2b').addService(googletag.pubads())
                            .defineSizeMapping(mappingLeaderboard);
                        googletag.enableServices();
                    },
                        function () { googletag.display('div-ad-home-btf-b2b'); });

                    googletag.cmd.push(function () {
                        googletag.defineSlot('/64852981/MP_Homepage_Leg_SR', [[160, 600]], 'div-ad-home-lft-b2b')
                            .addService(googletag.pubads())
                            .defineSizeMapping(mappingSkyscraper);
                        googletag.enableServices();
                    },
                        function () { googletag.display('div-ad-home-lft-b2b'); });
                }
            }*/
        }
    },
    finishInitialize: function () {
        $(".page-loader").hide();
        $(".regular3").slick({
            dots: true,
            infinite: true,
            prevArrow: '<button type="button" class="swiper-button-prev product-prev"></button>',
            nextArrow: '<button type="button" class="swiper-button-next product-next"></button>',
            slidesPerRow: 6,
            rows: 2,
            responsive: [
                {
                    breakpoint: 2000,
                    settings: {
                        slidesPerRow: 6,
                        rows: 2
                    }
                },
                {
                    breakpoint: 1024,
                    settings: {
                        slidesPerRow: 4,
                        rows: 2
                    }
                },
                {
                    breakpoint: 600,
                    settings: {
                        slidesPerRow: 2,
                        rows: 2
                    }
                },
                {
                    breakpoint: 480,
                    settings: {
                        slidesPerRow: 2,
                        rows: 2
                    }
                }
                // You can unslick at a given breakpoint now by adding:
                // settings: "unslick"
                // instead of a settings object
            ]
        });

        $(document).on('click',
            '#pauseButton',
            function (e) {
                $('#pauseButton').hide();
                $('#playButton').show();
                swiper.autoplay.stop();
            });
        $(document).on('click',
            '#playButton',
            function (e) {
                $('#playButton').hide();
                $('#pauseButton').show();
                swiper.autoplay.start();
            });

        $('#playButton').on('click touchstart',
            function () {
                $('#playButton').hide();
                $('#pauseButton').show();
                swiper.autoplay.start();
            });
        $('#pauseButton').on('click touchstart',
            function () {
                $('#pauseButton').hide();
                $('#playButton').show();
                swiper.autoplay.stop();
            });
        homePageStuff.someUnnamedFunction();
    },
    getUnbxdContent: function () {
        for (var i = 0; i < homePageStuff.contentFills.length; i++) {
            var outerItem = homePageStuff.contentFills[i];
            //wrap item in closure for after ajax call finishes.
            (function (item) {
                $(item.outerContainerSelector).hide();
                $.ajax({
                    url: item.url,

                    success: function (data) {
                        if (data) {
                            $(item.innerContainerSelector).html(data);
                            $(item.outerContainerSelector + " .product-item a").show();
                            $(item.outerContainerSelector + " .custom-loader").remove();
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
    initialize: function (options) {
        $(".loader,.page-loader").hide();
        $(".frequent-item").show();
        $(".custom-loader").remove();
        $(".home-layer5 *").css("opacity", "");       
        if (options.unbxdVersion === unbxdVersionValue) {
            homePageStuff.getUnbxdContent();
        }
        homePageStuff.finishInitialize();
    }
}

function checkSlides(sliderName,sliderCount) {   
    var slidesRowCount = 0;   
    if(sliderName == "#product-slider-regular1") {
        if(sliderCount <= 6) 
        {            
            swiper1.loopDestroy();                        
        }            
        slidesRowCount = swiper1.loopedSlides;       
    } 
    else if(sliderName == "#product-slider-regular2") {
        if(sliderCount <= 6) 
        {            
            swiper2.loopDestroy();                        
        } 
        slidesRowCount = swiper2.loopedSlides;        
    } 
    else if(sliderName == "#product-slider-regular3") {
        if(sliderCount <= 6) 
        {            
            swiper3.loopDestroy();                        
        }        
        slidesRowCount = swiper3.loopedSlides;       
    }  
    if(slidesRowCount < parseInt(sliderCount)) {
        $(sliderName+' .swiper-button-prev').show();
        $(sliderName+' .swiper-button-next').show();
        $(sliderName+' .swiper-pagination').show();
        $(sliderName+' .swiper-wrapper').removeClass("disabled");
    }
    else {
        $(sliderName+' .swiper-button-prev').hide();
        $(sliderName+' .swiper-button-next').hide();
        $(sliderName+' .swiper-pagination').hide();
        $(sliderName+' .swiper-wrapper').addClass("disabled");
        $(sliderName+' .swiper-slide-invisible-blank').remove();
    }
}

window.onload = function() {
     checkSlides('#product-slider-regular1',$("#product-slider-regular1").attr("data-total"));
     checkSlides('#product-slider-regular2',$("#product-slider-regular2").attr("data-total"));
     checkSlides('#product-slider-regular3',$("#product-slider-regular3").attr("data-total"));    
};               
