var ImageConfig = [
    /* Strip Banner */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.stripimage', parentclass: '.stripbanner', findtext: '.', replacetext: '768x150', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.stripimage', parentclass: '.stripbanner', findtext: '.', replacetext: '992x150', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.stripimage', parentclass: '.stripbanner', findtext: '.', replacetext: '1600x150', checkfromto: true, customlogic: false, dynamicheight: false },
    /* Left Banner */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.itemleft', parentclass: '.homebanner', findtext: '.', replacetext: '1190x1260', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.itemleft', parentclass: '.homebanner', findtext: '.', replacetext: '1190x1260', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.itemleft', parentclass: '.homebanner', findtext: '.', replacetext: '1770x570', checkfromto: true, customlogic: false, dynamicheight: false },
    /* Right Banner */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.itemright', parentclass: '.homebanner', findtext: '.', replacetext: '900x900', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.itemright', parentclass: '.homebanner', findtext: '.', replacetext: '900x900', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.itemright', parentclass: '.homebanner', findtext: '.', replacetext: '900x900', checkfromto: true, customlogic: false, dynamicheight: false },
    /* ATF 25% Banner(A) */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: ' .box-image', parentclass: '.sec-A', findtext: '.', replacetext: '570x300', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.box-image', parentclass: '.sec-A', findtext: '.', replacetext: '570x300', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.box-image', parentclass: '.sec-A', findtext: '.', replacetext: '570x300', checkfromto: true, customlogic: false, dynamicheight: false },
    /* ATF 50% Banner(B) */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.box-image', parentclass: '.sec-B', findtext: '.', replacetext: '600x750', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.box-image', parentclass: '.sec-B', findtext: '.', replacetext: '600x750', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.box-image', parentclass: '.sec-B', findtext: '.', replacetext: '1170x300', checkfromto: true, customlogic: false, dynamicheight: false },
    /* ATF 100% Banner(C) */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.box-image', parentclass: '.sec-C', findtext: '.', replacetext: '570x300', checkfromto: true, customlogic: false, dynamicheight: true },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.box-image', parentclass: '.sec-C', findtext: '.', replacetext: '570x300', checkfromto: true, customlogic: false, dynamicheight: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.box-image', parentclass: '.sec-C', findtext: '.', replacetext: '1975x200', checkfromto: true, customlogic: false, dynamicheight: false },
    /* BTF  */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 768, tovalidation: '<', classname: '.featured-layer1-first,.featured-layer1-middle,.featured-layer1-third,.featured-layer1-last', parentclass: '.featured-layer', findtext: '.', replacetext: '768x400', checkfromto: true, customlogic: false },
    { type: 'banner', fromsize: 769, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: '.featured-layer1-first,.featured-layer1-middle,.featured-layer1-third,.featured-layer1-last', parentclass: '.featured-layer', findtext: '.', replacetext: '496x400', checkfromto: true, customlogic: false },
    { type: 'banner', fromsize: 993, fromvalidation: '>', tosize: 5000, tovalidation: '<', classname: '.featured-layer1-first,.featured-layer1-middle,.featured-layer1-third,.featured-layer1-last', parentclass: '.featured-layer', findtext: '.', replacetext: '400x400', checkfromto: false, customlogic: false },
    /* ATF Custom */
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: 'sec-A,sec-B,sec-A', parentclass: '.box-layer', findtext: '.', replacetext: '570x300,600x750,570x300', checkfromto: true, customlogic: true },
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: 'sec-B,sec-A,sec-A', parentclass: '.box-layer', findtext: '.', replacetext: '600x750,570x300,570x300', checkfromto: true, customlogic: true },
    { type: 'banner', fromsize: 0, fromvalidation: '>', tosize: 992, tovalidation: '<', classname: 'sec-A,sec-A,sec-B', parentclass: '.box-layer', findtext: '.', replacetext: '570x300,570x300,600x750', checkfromto: true, customlogic: true },
];
$(document).ready(function () {
    $.each(ImageConfig, function (index, value) {
        ImageManipulation(value.fromsize, value.fromvalidation, value.tosize, value.tovalidation, value.classname, value.parentclass, value.findtext, value.replacetext, value.checkfromto, value.customlogic, value.dynamicheight);
    })
});
function ImageManipulation(fromSize, fromvalidation, toSize, tovalidation, className, parentclass, findText, ReplaceText, checkFromTo, customlogic, dynamicheight) {
    var width = $(window).outerWidth();
    if (customlogic == false) {
        if (checkFromTo == true) {
            var from = (fromvalidation == ">") ? ((parseInt(width) >= fromSize) ? true : false) : ((parseInt(width) <= fromSize) ? true : false);
            var to = (tovalidation == ">") ? ((parseInt(width) >= toSize) ? true : false) : ((parseInt(width) <= toSize) ? true : false);
            if (from && to) {
                if (dynamicheight) {
                    countLines();
                }
                var array = className.split(',');
                $(parentclass).each(function () {
                    var ti = this;
                    $.each(array, function (i, v) {
                        var url = $(ti).find(v).attr("data-img-url");
                        if (url != null) {
                            var n = url.lastIndexOf(findText);
                            url = [url.slice(0, n), ReplaceText, url.slice(n)].join('');
                            $(ti).find(v).find("img").attr("src", url);
                            $(ti).find(v).find("img").css("opacity", 1);
                            $(ti).find(v).removeClass("homepagecommon");
                            $(".slidercontent").css("opacity", 1);
                            $(".box-description").css("opacity", 1);
                            $(".featuredcontent").css("opacity", 1);
                        }
                    });
                });
            }
        }
        else {
            var from = (fromvalidation == ">") ? ((parseInt(width) >= fromSize) ? true : false) : ((parseInt(width) <= fromSize) ? true : false);
            if (from) {
                if (dynamicheight) {
                    countLines();
                }
                var array = className.split(',');
                $(parentclass).each(function () {
                    var ti = this;
                    $.each(array, function (i, v) {
                        var url = $(ti).find(v).attr("data-img-url");
                        if (url != null) {
                            var n = url.lastIndexOf(findText);
                            url = [url.slice(0, n), ReplaceText, url.slice(n)].join('');
                            $(ti).find(v).find("img").attr("src", url);
                            $(ti).find(v).find("img").css("opacity", 1);
                            $(ti).find(v).removeClass("homepagecommon");
                            $(".slidercontent").css("opacity", 1);
                            $(".box-description").css("opacity", 1);
                            $(".featuredcontent").css("opacity", 1);
                        }
                    });
                });
            }
        }
    }
    else {
        var from = (fromvalidation == ">") ? ((parseInt(width) >= fromSize) ? true : false) : ((parseInt(width) <= fromSize) ? true : false);
        var to = (tovalidation == ">") ? ((parseInt(width) >= toSize) ? true : false) : ((parseInt(width) <= toSize) ? true : false);
        if (from && to) {
            if (dynamicheight) {
                countLines();
            }
            var array = className.split(',');
            var existing_item = 0;
            $(parentclass).each(function (ins, val) {
                var found = "";
                var notfound = false;
                var t = this;
                var fullclass = "";
                $.each(array, function (i, v) {

                    if ($(t).find("div:nth-child(" + (i + 1) + ")").hasClass(array[i])) {

                        found = "." + $(t).attr('class').split(' ').pop();
                        fullclass = fullclass + array[i] + '-' + existing_item;
                        existing_item++;
                    }
                    else {

                        notfound = true;
                    }
                });
                if (notfound == false) {

                    $(t).addClass(fullclass);
                    $.each(array, function (i, v) {

                        var url = $("." + fullclass).find("div:nth-child(" + (i + 1) + ")").find(".box-image").attr("data-img-url");
                        var n = url.lastIndexOf(findText);
                        url = [url.slice(0, n), ReplaceText.split(',')[i], url.slice(n)].join('');
                        $("." + fullclass).find("div:nth-child(" + (i + 1) + ")").find(".box-image").find("img").attr("src", url);
                        $("." + fullclass).find("div:nth-child(" + (i + 1) + ")").find(".box-image").find("img").css("opacity", 1);
                        $("." + fullclass).find("div:nth-child(" + (i + 1) + ")").find(".box-image").removeClass("homepagecommon");
                        $(".box-description").css("opacity", 1);
                        $(".featuredcontent").css("opacity", 1);
                    });
                }
            });


        }
    }
}
$(document).ready(function () {
    var width = $(window).outerWidth();
    if (parseInt(width) > 992) {
        calculateAspectRatioFit($(".itemleft img").width(), $(".itemleft img").height(), $(".herobanner").width(), $(".herobanner").height());
    }
    if (parseInt(width) < 768) {
        countLines();
    }
    $(window).resize(function () {

        $.each(ImageConfig, function (index, value) {
            ImageManipulation(value.fromsize, value.fromvalidation, value.tosize, value.tovalidation, value.classname, value.parentclass, value.findtext, value.replacetext, value.checkfromto, value.customlogic, value.dynamicheight);
           
        });
    });
    function resizeStuff() {
        //Time consuming resize stuff here
        if (parseInt(width) > 992) {
          calculateAspectRatioFit($(".itemleft img").width(), $(".itemleft img").height(), $(".herobanner").width(), $(".herobanner").height());
        }
    }
    var TO = null;
    $(window).resize(function () {
        if ($(".itemleft img").width() != $(".itemright img").width()) {
            TO = setInterval(resizeStuff, 10); //10 is time in miliseconds
        }
        else {
            clearInterval(TO); // stop the interval
        }
    });
});
function countLines() {
    $(".boxdescdata h2").each(function () {
        var divHeight = $(this).first().outerHeight();
        var lineHeight = parseInt($(this).css('line-height'));
        var lines = divHeight / lineHeight;
        var t = this;
        $(t).parent().parent().parent().parent().removeClass("oneline");
        $(t).parent().parent().parent().parent().removeClass("twoline");
        $(t).parent().parent().parent().parent().removeClass("threeline");
        if (Math.round(lines) == 1) {
            $(t).parent().parent().parent().parent().addClass("oneline");
        }
        if (Math.round(lines) == 2) {
            $(t).parent().parent().parent().parent().addClass("twoline");
        }
        if (Math.round(lines) == 3) {
            $(t).parent().parent().parent().parent().addClass("threeline");
        }
    });
}
function calculateAspectRatioFit(srcWidth, srcHeight, maxWidth, maxHeight) {
    var widthSize = $(window).outerWidth();
   
    if (parseInt(widthSize) > 992) {
        var ratio = Math.min(maxWidth / srcWidth, maxHeight / srcHeight);
        $(".itemright img").css("height", srcHeight * ratio);
    }
    else {
        $(".itemright img").css("height", "auto");
    }
}
