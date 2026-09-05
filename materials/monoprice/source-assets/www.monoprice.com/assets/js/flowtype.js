$(document).ready(function () {
    //slider touch
    // $("#hp-hero-rotator").bcSwipe({ threshold: 40 });

    //responsive text
    $('.home-content h2, .cat-slider .carousel-caption h2').flowtype({
        minimum: 300,
        maximum: 1000,
        fontRatio: 15
    }).css('visibility', 'visible');
    $('.home-content p, .cat-slider .carousel-caption p').flowtype({
        minimum: 300,
        maximum: 500,
        fontRatio: 25
    }).css('visibility', 'visible');
    $('.hp-modules h2').flowtype({
        minimum: 200,
        maximum: 500,
        fontRatio: 15
    });
    $('.hp-modules p').flowtype({
        minimum: 200,
        maximum: 500,
        fontRatio: 20
    }).css('visibility', 'visible');
    $('h2.cat-block-title').flowtype({
        minimum: 200,
        maximum: 1000,
        minFont: 12,
        maxFont: 40
    }).css('visibility', 'visible');

    // about us page
    $('.about-slider-caption p').flowtype({
        minimum: 300,
        maximum: 1000,
        fontRatio: 18
    });

    function colEquiHeight() {
        var maxHeight = 0,
            itemHeight = 0,
            headerCaption;

        $('.col-cell').each(function () {
            $(this).removeAttr('style');
            var itemHeight = parseInt($(this).outerHeight());
            if (itemHeight > maxHeight) maxHeight = itemHeight;
        });

        $('.col-cell').css('height', maxHeight);

        headerCaption = $('.about-slider-caption');
        headerCaption.removeAttr('style');
        headerCaption.height(headerCaption.find('p').innerHeight());
    }

    $(window).on('load resize', colEquiHeight);

    //svg
    svgeezy.init(false, 'png');

    var list = $('.fti-prod-row');
    var items = list.find('.bs-prod-desc');

    var setHeights = function () {
        items.css('height', 'auto');

        var perRow = Math.floor(list.width() / items.width());

        if (perRow == null || perRow < 2) return true;

        for (var i = 0, j = items.length; i < j; i += perRow) {
            var maxHeight = 0,
                row = items.slice(i, i + perRow);

            row.each(function () {
                var itemHeight = parseInt($(this).outerHeight());
                if (itemHeight > maxHeight) maxHeight = itemHeight;
            });
            row.css('height', maxHeight);
        }
    };

    var itemsList = $('.ft-cat-carousel').find('.ft-prod').length;
    if (itemsList < 4) {
        $('.ft-cat-carousel .owl-nav').hide();
    }
});