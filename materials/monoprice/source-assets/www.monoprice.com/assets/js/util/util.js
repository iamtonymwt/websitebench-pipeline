define(function () {

	var validators = {};

	validators.emailValidator = function (str) {
		var regex = /^(([a-zA-Z]|[0-9])|([-]|[_]|[.]))+[@]((([a-zA-Z0-9])|([-])){2,63}[.])+(([a-zA-Z0-9]){2,63})+$/;

		return str ? regex.test(str) : {
			regex: regex
		}
	};

	var timer = (function () {
		var timers = {};
		return function (timerId, callback, ms) {
			if (!timerId) return false;
			if (timers[timerId]) clearTimeout(timers[timerId]);
			timers[timerId] = setTimeout(callback, ms);
		};
	})();

	function getUrlParameter(sParam) {
	  var sPageURL = decodeURIComponent(window.location.search.substring(1)),
	      sURLVariables = sPageURL.split('&'),
	      sParameterName,
	      i;

	  for (i = 0; i < sURLVariables.length; i++) {
	      sParameterName = sURLVariables[i].split('=');

	      if (sParameterName[0] === sParam) {
	          return sParameterName[1] === undefined ? true : sParameterName[1];
	      }
	  }
	}

	return {
		timer: timer,
		getUrlParameter: getUrlParameter,
		validators: validators
	};
});