var submit = document.querySelector('input[type="submit"]');
var form = document.querySelector('#checkout-form');

braintree.client.create({
  authorization: token
}, function (clientErr, clientInstance) {
  if (clientErr) {
    // Handle error in client creation
    console.log(clientErr);
    return;
  }

  braintree.hostedFields.create({
    client: clientInstance,
    styles: {
      'input': {
        'font-size': '14pt'
      },
      'input.invalid': {
        'color': 'red'
      },
      'input.valid': {
        'color': 'green'
      }
    },
    fields: {
      number: {
        selector: '#card-number',
        placeholder: '4111 1111 1111 1111'
      },
      cvv: {
        selector: '#cvv',
        placeholder: '123'
      },
      expirationDate: {
        selector: '#expiration-date',
        placeholder: '10/2019'
      }
    }
  }, function (hostedFieldsErr, hostedFieldsInstance) {
    if (hostedFieldsErr) {
      // Handle error in Hosted Fields creation
      console.log('hostedFieldsErr');
      console.log(hostedFieldsErr);
      return;
    }
    console.log('Enabling submit btn');
    submit.removeAttribute('disabled');
    form.addEventListener('submit', function (event) {
      event.preventDefault();

      hostedFieldsInstance.tokenize(function (tokenizeErr, payload) {
        if (tokenizeErr) {
          // Handle error in Hosted Fields tokenization
          console.log('tokenizeErr');
          console.log(tokenizeErr);
          return;
        }

        // Put `payload.nonce` into the `payment-method-nonce` input, and then
        // submit the form. Alternatively, you could send the nonce to your server
        // with AJAX.
        document.querySelector('input[name="payment-method-nonce"]').value = payload.nonce;
        console.log('submitting form');
        form.submit();
      });
    }, false);
  });
});
