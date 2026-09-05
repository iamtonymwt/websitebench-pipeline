(function($) {
    //options: msg, modal, onConfirm, onCancel
    function confirm(e, options) {
        e.preventDefault();

        var $confirm = $('#mpi-modal-confirm'),
            ret;

        $.fancybox.open($confirm, {
            modal: options.modal,
            beforeShow: function() {
                $confirm.find('.mpi-modal-confirm-title').html(options.title);
                $confirm.find('.mpi-modal-confirm-msg').html(options.msg);
            },
            afterShow: function() {

                $confirm.on('click', function(e) {
                    e.preventDefault();

                    if ($(e.target).is('.mpi-modal-confirm-confirmed')) {
                        options.onConfirm.call(this);
                    } else if ($(e.target).is('.mpi-modal-confirm-cancel')) {
                        options.onCancel.call(this);
                    }
                    $.fancybox.close();
                });
            },
            destroy: function () {
                $confirm.off('click');
            }
        });
    }

    $.fn.fancyboxConfirm = function(options) {
        return this.each(function() {
            $(this).on('click', function(e) {
                confirm(e, options);
            });
        });
    };
})(jQuery);