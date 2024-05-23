<script>
import { MDBFooter, MDBContainer, MDBRow, MDBCol, MDBBtn, MDBIcon } from 'mdb-vue-ui-kit';

export default {
    components: {
        MDBFooter,
        MDBContainer,
        MDBRow,
        MDBCol,
        MDBBtn,
        MDBIcon
    },
};
</script>

<template>
      <main>
          <!-- This page directs people to the photography, tech or company sections of the site, located at photo.benkyd.co.uk, tech.benkyd.co.uk and company.benkyd.co.uk respectively -->
          <!-- The routing and hosting for these sections is handled by nginx reverse proxy which  is configured to direct traffic to the correct subdomain -->

          <MDBNavbar light bg="light" expand="lg" container>
          <MDBNavbarBrand href="#">Navbar</MDBNavbarBrand>
          <MDBNavbarToggler
          target="#navbarNav"
          @click="collapse2 = !collapse2"
          ></MDBNavbarToggler>
          <MDBCollapse id="navbarNav" v-model="collapse2">
          <MDBNavbarNav>
          <MDBNavbarItem to="#" active> Home </MDBNavbarItem>
          <MDBNavbarItem to="#"> Features </MDBNavbarItem>
          <MDBNavbarItem to="#"> Pricing </MDBNavbarItem>
          <MDBNavbarItem to="#" disabled> Disabled </MDBNavbarItem>
          </MDBNavbarNav>
          </MDBCollapse>
          </MDBNavbar>

          <h1>Welcome to Benkyd.co.uk</h1>

          <hr class="hr" />

          <li><a href="https://photo.benkyd.co.uk">Photography</a></li>
          <li><a href="https://tech.benkyd.co.uk">Tech</a></li>
          <li><a href="https://ben-labs.co.uk">Ben Labs</a></li>

          <MDBFooter bg="dark" :text="['center', 'white']">
          <!-- Grid container -->
          <MDBContainer class="p-4 pb-0">
          <!-- Section: Social media -->
          <section class="mb-4">
              <!-- Instagram -->
              <MDBBtn
              tag="a"
              outline="light"
              href="#!"
              floating
              class="m-1"
              >
              <MDBIcon iconStyle="fab" icon="instagram"></MDBIcon>
              </MDBBtn>
              <!-- Linkedin -->
              <MDBBtn
              tag="a"
              outline="light"
              href="#!"
              floating
              class="m-1"
              >
              <MDBIcon iconStyle="fab" icon="linkedin-in"></MDBIcon>
              </MDBBtn>
              <!-- Github -->
              <MDBBtn
              tag="a"
              outline="light"
              href="#!"
              floating
              class="m-1"
              >
              <MDBIcon iconStyle="fab" icon="github"></MDBIcon>
              </MDBBtn>
          </section>
          <!-- Section: Social media -->
          </MDBContainer>
          <!-- Grid container -->
          <!-- Copyright -->
          <div
              class="text-center p-3"
              style="background-color: rgba(0, 0, 0, 0.2)"
              >
              © 2020 Copyright:
              <a class="text-white" href="https://mdbootstrap.com/"
                  >MDBootstrap.com</a
              >
          </div>
                  <!-- Copyright -->
          </MDBFooter>

      </main>
</template>

<style scoped>
main {
    display: flex;
    flex-direction: column;
    place-items: center;
    padding: var(--section-gap);
    text-align: center;
}

header {
    line-height: 1.5;
}

@media (min-width: 1024px) {
  header {
      display: flex;
      place-items: center;
      padding-right: calc(var(--section-gap) / 2);
  }

  header .wrapper {
      display: flex;
      place-items: flex-start;
      flex-wrap: wrap;
  }
}
</style>
