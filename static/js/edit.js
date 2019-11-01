function confirmDelete() {
  if (confirm('Are you sure you want to permanently delete this site? ' +
              'Your login information will also be deleted.')) {
    signOut();
  }
  return false;
}

function uploadSong() {
  $('#song-error-cont').html('');

  $.ajax({
    xhr: function() {
      var xhr = new window.XMLHttpRequest();      
      xhr.upload.addEventListener("progress", function(evt) {
        if (evt.lengthComputable) {
          var percentComplete = Math.floor(evt.loaded * 100 / evt.total);
          console.log(percentComplete);

          if (percentComplete === 100) {
            console.log('done');
          }

        }
      }, false);

      return xhr;
    },
    url: '/upload',
    type: "POST",
    data: new FormData($('#song-form').get(0)),
    contentType: false,
    processData: false,
    error: function(result) {
          $('#song-error-cont').append(
            '<div class="alert alert-danger" role="alert">' +
            'An error occurred.</div>');
    },
    success: function(result) {
      if (result['errors']) {
        for (var i = 0; i < result['errors'].length; i++) {
          $('#song-error-cont').append(
            '<div class="alert alert-danger" role="alert">' +
            result['errors'][i] + '</div>');
        }
      } else {
        document.location.reload();
      }
    }
  });
}

$.oauthpopup = function(options) {
  options.windowName = 'ConnectWithOAuth'; // should not include space for IE
  options.windowOptions = 'location=0,status=0,width=800,height=400';
  options.callback = options.callback || function() {
    window.location.reload();
  };

  var that = this;
  that._oauthWindow = window.open(
    options.path, options.windowName, options.windowOptions);
  that._oauthInterval = window.setInterval(function(){
    if (that._oauthWindow.closed) {
      window.clearInterval(that._oauthInterval);
      options.callback();
    }
  }, 1000);
};

function netlifyPopup() {
  $('#netlify-error').hide();
  $.oauthpopup({
    path: ('https://app.netlify.com/authorize?response_type=token' +
      '&client_id=' + NETLIFY_CLIENT_ID +
      '&redirect_uri=https%3A%2F%2Frainfall.dev%2Foauth2'),
    callback: function() {
      $.ajax({
        dataType: 'json',
        url: '/netlify_token',
        success: function(data) {
          $('#netlify-step-1').hide();
          if (data.token) {
            NETLIFY_ACCESS_TOKEN = data.token;
            $('#netlify-step-2').show();
          } else {
            $('#netlify-error').show();
          }
        },
        error: function(data) {
          $('#netlify-step-1').hide();
          $('#netlify-error').show();
        }
      });
    }
  });
}


$(function() {
  function updateFromHash() {
    var hash = location.hash || '#new';

    $('.section').hide();
    $(hash).show();

    $('.nav-item').removeClass('active');
    $(hash + '-nav').addClass('active');
  }

  $(window).on('hashchange', updateFromHash);
  updateFromHash();

  $(document).on('change', '.custom-file-input', function () {
    let fileName = $(this).val().replace(/\\/g, '/').replace(/.*\//, '');
    $(this).parent('.custom-file').find('.custom-file-label').text(fileName);
  });
});
