function CustomTabbingForSlider(SliderName, Prev, Next, SwiperName) {     
    var qty = 6;   
    if ($(window).width() <= 1024) {
        qty = 5;
    }
    else if ($(window).width() <= 768) {
        qty = 3;
    }
    else if ($(window).width() <= 640) {
        qty = 2;
    }
    $(Next).on("keydown", "a:first", function (e) {
        if (e.keyCode == 9 && e.shiftKey) {
            SwiperName.slideToLoop(0);
            $(SliderName).find(".swiper-wrapper").find(".swiper-slide-active").find("a").focus();                     
        }
    });
    $(SliderName).on("keyup", ".swiper-slide", function (e) {
        var total = $(SliderName).attr("data-total");
        var keyCode = e.keyCode || e.which;           
        var index = $(this).index() - (qty - 1);    
        var a = 0;                                 
        if (keyCode == 9 && e.shiftKey && !$(this).hasClass("swiper-slide-active")) {                  
            if ($(this).attr("data-swiper-slide-index") == (total - 1)) {                  
                if((SliderName == "#product-slider-regular2") || (SliderName == "#product-slider-regular3")) //recommended section 
                {
                    $(".home-layer2").find("a").focus(); //slotATF
                }                    
                if(SliderName == "#product-slider-regular1") 
                {
                    $(".home-layer6").find("a").focus();
                }
                return false;
            }
            else {              
                SwiperName.slideToLoop($(this).attr("data-swiper-slide-index")-1);                               
            }
        }
        else {                 
            if (index <= parseInt(total - 1)) {

                if ($(this).hasClass("swiper-slide-duplicate") && $(this).attr("data-swiper-slide-index") != (total - 1)) {                   
                    $(SliderName).find(".swiper-wrapper").find(".swiper-slide-active").find("a").focus();                                  
                }

                if (keyCode == 9) {
                  
                    $(SliderName).find(".swiper-wrapper").find(".swiper-slide").each(function () {
                        if ($(this).hasClass("swiper-slide-active")) {                           
                            a = $(this).index();                           
                        }
                    });                     
                    if (a > 0) { 
                        if (index == a) {                                   
                            $(SliderName).find(".swiper-button-next").trigger("click");                            
                        }                                                                                                                                      
                    }                                       
                }
            }   
            else if(index == total) {              
                 if ($(this).hasClass("swiper-slide-duplicate") && $(this).attr("data-swiper-slide-index") == (total-1)) {                   
                    $(SliderName).find(".swiper-wrapper").find(".swiper-slide-active").find("a").focus();                                  
                 }
            }
            else {
                $(Next + " a:first").focus();
            }                       
    }                  
    });  
}

// Arrow icon  = Carousels should not have arrow navigation when only one set is available and no swipe 
$(document).ready(function () {
    //allow use for dom elements that have not been created yet
    $(document).on('hover', '.swiper-container', function () {
        if ($(this).attr("data-total") <= 6) {
            $(this).find('.swiper-button-next').css('display', 'none');
            $(this).find('.swiper-button-prev').css('display', 'none');
            $(this).find('.product-next').css('display', 'none');
            $(this).find('.product-prev').css('display', 'none');
        }
        else {
            $(this).find('.swiper-button-next').css('display', 'block');
            $(this).find('.swiper-button-prev').css('display', 'block');
            $(this).find('.product-next').css('display', 'block');
            $(this).find('.product-prev').css('display', 'block');
        }
    }, function () {
            $(this).find('.swiper-button-next').css('display', 'none');
            $(this).find('.swiper-button-prev').css('display', 'none');
            $(this).find('.product-next').css('display', 'none');
            $(this).find('.product-prev').css('display', 'none');
        });
    var qty = 6;
    if ($(window).width() >= 1024) {
        qty = 6;
    }
    else if ($(window).width() <= 768) {
        qty = 3;
    }
    else if ($(window).width() <= 640) {
        qty = 2;
    }  
    if ($('#product-slider-regular3').attr("data-total") <= qty) {
        $($('#product-slider-regular3').find('.swiper-wrapper')).addClass('disabled')
        $($('#product-slider-regular3').find('.swiper-pagination')).addClass('disabled')
    }
    if ($('#product-slider-regular2').attr("data-total") <= qty) {
        $($('#product-slider-regular2').find('.swiper-wrapper')).addClass('disabled')
        $($('#product-slider-regular2').find('.swiper-pagination')).addClass('disabled')
    }    
    if ($('#product-slider-regular1').attr("data-total") <= qty) {
        $($('#product-slider-regular1').find('.swiper-wrapper')).addClass('disabled')
        $($('#product-slider-regular1').find('.swiper-pagination')).addClass('disabled')
    }
});