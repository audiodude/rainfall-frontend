function confirmDelete() {
  if (confirm('Are you sure you want to permanently delete this site? ' +
              'Your login information will also be deleted.')) {
    signOut();
  }
  return false;
}

function uploadSong() {
  console.log(new FormData($('#song-form').get(0)));
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
    success: function(result) {
      console.log(result);
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
