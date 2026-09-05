(function ($) {

  if (!window.enableEmailPopup)
    return;

  var pageLoadtimeId = null;

  $(window).on('load', function () {
    pageLoadtimeId = setTimeout(function () {
      if (isLocalStorageNameSupported() && localStorage.getItem("popup") == null) {
        $('a.btn-promo-modal').trigger('click');
        $("#input-21").val('');

        var data = [];
        data.push({ "closed": 0 });
        localStorage.setItem("popup", JSON.stringify(data));
      }
    }, 50);

    // Check popup data, show side button if its not signed up before.
    if (isLocalStorageNameSupported() && localStorage.getItem("popup") !== null) {
      var isSubmitted = false;
      var popupData = JSON.parse(localStorage.getItem("popup"));
      $.each(popupData, function (i) {
        if (popupData[i]["submitted"] == 1) {
          isSubmitted = true;
        }
      });

      if (!isSubmitted) {
        $('a.btn-promo-modal').show();
      }
    }
  });

  var timeoutID = null;

  $('a.btn-promo-modal').fancybox({
    'openEffect': 'elastic',
    'closeEffect': 'elastic',
    'speedIn': 1500,
    'speedOut': 1500,
    'maxWidth': 500,
    'padding': 0,
    'closeBtn': true,
    'height': 'auto',
    'beforeLoad': function () {
      $("#input-21").val('');
      $(".promo-content .input--filled").removeClass("input--filled");
      if ($('.promo-label h2.error-msg').length > 0) {
        $('.promo-label h2').remove();
        $('.promo-label').html('<h2>SIGN UP FOR EMAIL DEALS</h2>');
      }
    },
    'afterShow': function () {
      $('a.btn-promo-modal').hide();
      clearTimeout(pageLoadtimeId);
      pageLoadtimeId = null;
    },
    'beforeClose': function () {
      $('.fancybox-lock').removeClass('fancybox-lock');
      $('a.btn-promo-modal').show();
    },
    tpl: {
      closeBtn: '<a title="Close" class="fancybox-item fancybox-close" href="javascript:;">✕</a>'
    }
  });

  $('#emailsubscribeform').on('submit', function (e) { email_popup(); e.preventDefault(); });

  function clearAllTimer() {
    clearTimeout(pageLoadtimeId);
    pageLoadtimeId = null;
    clearTimeout(timeoutID);
    timeoutID = null;
  }

  function startTimer() {
    timeoutID = window.setTimeout(function () {
      $('.fancybox-close').trigger('click');
    }, 4000);
  }

  function resetTimer() {
    clearTimeout(timeoutID);
    timeoutID = null;
    startTimer();
  }

  function email_popup() {
    clearAllTimer();
    var data = [];

    if (isLocalStorageNameSupported() && localStorage.getItem("popup") != null) {
      data = JSON.parse(localStorage.getItem("popup"));
      data.push({ "submitted": 1 });
    }
    else {
      data.push({ "submitted": 1 });
    }
    if (isLocalStorageNameSupported()) {
      localStorage.setItem("popup", JSON.stringify(data));
    }
    var vemailaddress = $("#input-21").val();
    var validEmail = /^[a-zA-Z0-9][\w\.-]*[a-zA-Z0-9]@[\w-\.]*[a-zA-Z0-9]\.[a-zA-Z]{2,7}$/;
    if (vemailaddress == '') {
      $("div.promo-label.clr-link").html("<h2>Please enter Email address.</h2>");
    } else if (vemailaddress !== '' && !validEmail.test(vemailaddress)) {
      $("div.promo-label.clr-link").html("<h2>Please enter valid Email address.</h2>");
    } else {
      $("#subscribetoemail").prop("disabled", true);
      var newsLetterAjax = $.ajax({
          type: "POST",
          url: '/Home/EmailSubcription?email_address=' + vemailaddress,
        beforeSend: function () {
          $('#emailsubscribeform .fa-envelope-o').addClass('hidden');
          $('.fa-circle-o-notch').removeClass('hidden');
          $(document).off('mousemove mousedown scroll mousewheel resize');
        },
        success: function (result) {
            $('#emailsubscribeform .fa-envelope-o').removeClass('hidden');
            $('#emailsubscribeform .fa-envelope-o').focus();
          $('.fa-circle-o-notch').addClass('hidden');
          $("#input-21").val('');
          $("div.promo-label.clr-link").html("<h2>" + result + "</h2>");
          $("div.promo-label.clr-link").focus();
          $('.btn-promo-modal, #frmPromo').addClass('hidden');
          $("#subscribetoemail").prop("disabled", false);
        },
        error: function () {
          $('#emailsubscribeform .fa-envelope-o').removeClass('hidden');
          $('.fa-circle-o-notch').addClass('hidden');
          $("#input-21").val('');
          $(".promo-content .input--filled").removeClass("input--filled");
          $("div.promo-label.clr-link").html("<h2 class='error-msg'>Something went wrong.</h2>");
          $("div.promo-label.clr-link").focus();
          localStorage.removeItem("popup");
          var data = [];
          data.push({ "closed": 0 });
          localStorage.setItem("popup", JSON.stringify(data));
          $("#subscribetoemail").prop("disabled", false);
        }
      });
      newsLetterAjax.done(function () { resetTimer(); });
      newsLetterAjax.fail(function () { resetTimer(); });
    }
    return false;
  }

  // To test private browsing mode while using localStorage (ios mainly)	
  function isLocalStorageNameSupported() {
    var testKey = 'test', storage = window.sessionStorage;
    try {
      storage.setItem(testKey, '1');
      storage.removeItem(testKey);
      return true;
    }
    catch (error) {
      if (error.code === DOMException.QUOTA_EXCEEDED_ERR && storage.length === 0) {
        return false;
      }
    }
  }
})(jQuery);
